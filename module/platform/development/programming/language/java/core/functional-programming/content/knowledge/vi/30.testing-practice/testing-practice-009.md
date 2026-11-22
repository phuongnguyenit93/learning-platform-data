# Thực hành sửa pipeline dùng trạng thái bên ngoài hoặc `reduce()` sai trong Java

## 1. Bài thực hành này giải quyết vấn đề gì?

Java Stream giúp biểu đạt thao tác biến đổi và tổng hợp dữ liệu bằng các bước `filter`, `map`, `reduce` và `collect`. Tuy nhiên, một pipeline **chạy được ở chế độ tuần tự** chưa chắc **đúng về hợp đồng**, đặc biệt khi chuyển sang `parallel()`. Hai nguồn lỗi điển hình là:

1. **Trạng thái bên ngoài thay đổi được (external mutable state)**: lambda đọc/ghi một `ArrayList`, `Map`, bộ đếm, mảng một phần tử hoặc đối tượng cấu hình được chia sẻ; các bước không còn độc lập, và song song hóa có thể tạo race condition.
2. **Dùng `reduce()` sai**: chọn toán tử không kết hợp, chọn identity không trung hòa, dùng combiner không tương thích accumulator, hoặc dùng một object mutable chung làm identity rồi mutate nó.

Bài này thuộc nhóm **Kiểm thử và thực hành**. Thay vì chỉ thuộc lý thuyết, mỗi tình huống được trình bày theo lộ trình **đọc mã lỗi → giải thích nguyên nhân → refactor → kiểm tra lại**, kèm một chương trình Java 17 hoàn chỉnh và bộ kiểm tra có kết quả xác định.

Sau khi hoàn thành, bạn sẽ:

- Phân biệt callback *stateless*, *non-interfering* với callback sử dụng mutable state.
- Nhận diện sự khác nhau giữa **mutate nguồn đang duyệt** và **mutate accumulator chung bên ngoài**.
- Sửa các pipeline thu List, tổng, histogram, đánh số thứ tự và nối chuỗi theo API reduction/collector phù hợp.
- Kiểm tra phép toán kết hợp, identity, accumulator/combiner trước khi dùng `reduce`.
- Tránh dùng `AtomicInteger` hoặc `synchronizedList` để che một thiết kế stateful không cần thiết.
- Phân biệt kết quả ordered Stream với thứ tự **side effect** của `parallel().forEach`.
- Viết test có thể lặp lại, không dựa vào race condition xuất hiện đúng lần chạy.
- Xử lý ca rỗng, dữ liệu lặp, số âm, overflow và khác biệt của cộng số thực.

Các đoạn ghi **“Sai có chủ đích”** nhằm phân tích, không khuyến khích chạy trên hệ thống có dữ liệu thật.

## 2. Ba điều kiện kiểm tra trước khi chuyển sang parallel

### 2.1. Non-interference: không can thiệp nguồn

Một behavioral parameter của Stream (lambda/method reference) nói chung không được sửa **nguồn đang được duyệt**, trừ trường hợp nguồn được thiết kế riêng cho việc thay đổi đồng thời với semantics rõ. Ví dụ, callback duyệt `ArrayList` mà lại `add`/`remove` chính List đó là vi phạm nguyên tắc này.

### 2.2. Stateless: không dựa vào trạng thái thay đổi giữa các lần gọi

Lambda `n -> n*n` chỉ phụ thuộc `n`; ngược lại lambda `n -> counter.getAndIncrement() + ":" + n` phụ thuộc vào bộ đếm chia sẻ và scheduling của worker. Có thể dùng hằng số hoặc cấu hình immutable ổn định được capture; **stateless không có nghĩa cấm đọc mọi biến ngoài**. Điều cần tránh là kết quả của callback phụ thuộc vào trạng thái mutable đang thay đổi giữa những lần xử lý.

### 2.3. Associativity và identity cho reduction

Phép gộp hai ngôi `⊕` phải kết hợp:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Identity `e` phải trung hòa:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

Ví dụ cộng số nguyên có identity `0`; phép nhân có identity `1`; phép nối chuỗi có identity `""`. **Phép trừ không kết hợp**, và `10` không phải identity của phép cộng chỉ vì bài toán muốn “cộng thêm 10”.

Với overload `reduce(identity, accumulator, combiner)`, combiner còn phải tương thích với accumulator. Chia dữ liệu thành nhánh riêng rồi gộp phải cho cùng ý nghĩa với tích lũy trực tiếp.

### 2.4. Bảng chẩn đoán nhanh

| Dấu hiệu trong code | Vấn đề cần hỏi | Hướng sửa thường phù hợp |
| --- | --- | --- |
| `stream().forEach(shared::add)` | Có accumulator ngoài được nhiều callback mutate? | `toList()` hoặc `collect(toCollection(...))` |
| `parallel().forEach(n -> sum[0] += n)` | Phép cập nhật có race không? | `sum()` hoặc `reduce` hợp lệ |
| `map(n -> counter.getAndIncrement())` | Output có phụ thuộc thứ tự worker? | Nguồn chỉ số `IntStream.range` hoặc thay mô hình |
| `map(x -> { source.remove(x); ... })` | Có mutate chính source không? | Tạo kết quả mới, lọc thay vì xóa nguồn |
| `reduce(10,Integer::sum)` | Identity có trung hòa không? | `reduce(0,Integer::sum)` rồi cộng 10 |
| `reduce(0,(a,b)->a-b)` | Phép toán có kết hợp không? | Dùng phép đúng hoặc ordered fold ngoài Stream |
| `reduce(new StringBuilder(), ...append...)` | Có dùng mutable identity sai hợp đồng? | `Collectors.joining()` hoặc `collect` đúng |
| `reduce(0,Integer::sum,(a,b)->a-b)` | Combiner có tương thích accumulator không? | Gộp nhất quán bằng cộng |
| `parallel().forEach(System.out::println)` | Có đang đòi thứ tự side effect không? | `forEachOrdered` hoặc thu List rồi in |

## 3. Bài sửa số 1 — Thu List bằng trạng thái bên ngoài

### 3.1. Mã lỗi có chủ đích

~~~java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 1000)
        .parallel()
        .forEach(output::add);
~~~

Đoạn này đặt trong method có import `List`, `ArrayList` và `IntStream`. Nó có thể biên dịch, nhưng **không an toàn**: nhiều task cùng ghi vào một `ArrayList` không đồng bộ. Các thao tác thêm có thể tranh chấp, làm mất phần tử, tạo trạng thái hỏng hoặc ném exception. Việc một vài lần chạy cho đúng 1000 phần tử **không chứng minh** nó an toàn.

Nếu chỉ chạy tuần tự, code có thể có vẻ đúng; song nguyên tắc của Stream là nên diễn đạt phép thu bằng terminal operation để tránh accumulator ngoài.

### 3.2. Sửa đúng: thu thành List

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();
~~~

`IntStream.range(0,1000)` tạo nguồn có encounter order từ 0 đến 999. `boxed()` chuyển `int` thành `Integer`. `Stream.toList()` trong Java 17 trả List unmodifiable theo encounter order khi có, vì thế đầu ra có 1000 phần tử đúng thứ tự.

Nếu sau khi thu **cần List mutable**:

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

output.add(1000);
~~~

`toCollection(ArrayList::new)` xác định implementation mutable rõ. Stream framework quản lý accumulator/combiner theo hợp đồng collector; khác với việc callback tùy ý ghi vào một List chung bên ngoài.

**Điểm phân biệt:** việc pipeline song song thu đúng không làm `ArrayList` trả về tự trở thành thread-safe nếu nhiều thread tiếp tục mutate nó sau `collect`.

### 3.3. Bài kiểm thử

Thay vì chạy mã lỗi 100 lần để “chờ nó sai”, hãy kiểm tra tính đúng của phiên bản sửa:

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();

if (output.size() != 1000
        || output.get(0) != 0
        || output.get(999) != 999) {
    throw new AssertionError("wrong result");
}
~~~

Đây là mảnh mã trong method. Test không dựa vào race timing; nó mô tả **hợp đồng kết quả** mong muốn.

## 4. Bài sửa số 2 — Cộng tổng bằng biến/mảng dùng chung

### 4.1. Biến local gán lại trong lambda

~~~java
int sum = 0;

IntStream.rangeClosed(1, 100)
        .forEach(n -> sum += n);
~~~

Đây là **mã không biên dịch**: local `sum` bị gán lại trong lambda nên không effectively final. Lỗi compiler là một tín hiệu hữu ích, không phải lời mời dùng mảng một phần tử để né giới hạn capture.

### 4.2. Mảng một phần tử không giải quyết concurrency

~~~java
int[] holder = {0};

IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(n -> holder[0] += n);
~~~

Đoạn này biên dịch, nhưng cập nhật `holder[0]` **không atomic**: phép đọc → cộng → ghi có thể xen kẽ giữa các thread. Kết quả có thể không phải 500500, và race không bắt buộc sinh exception.

### 4.3. Sửa đúng: reduction có hợp đồng

~~~java
int sum = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

System.out.println(sum); // 500500
~~~

Hoặc:

~~~java
int sum = IntStream.rangeClosed(1, 1000)
        .parallel()
        .reduce(0, Integer::sum);
~~~

`0` là identity của cộng; phép cộng `int` kết hợp theo số học Java modulo 2^32. Với miền 1..1000, không overflow nên đúng cả kết quả toán học. Nếu tổng có thể vượt phạm vi `int`, chuyển sang kiểu phù hợp:

~~~java
long sum = IntStream.rangeClosed(1, 100_000)
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
~~~

`IntStream.sum()` cũng có thể overflow mà không ném exception. Chỉ chuyển sang `long` khi dữ liệu phù hợp, và vẫn phải xem giới hạn `long` với các miền lớn.

### 4.4. Câu hỏi tự kiểm tra

Tại sao `AtomicInteger.addAndGet(n)` không được ưu tiên ở đây? Nó có thể làm cập nhật atomic nhưng vẫn là side effect lên shared state, tạo tranh chấp, khó composition và không còn biểu đạt trực tiếp phép reduction. `sum()` nói rõ mục tiêu và để framework xử lý song song theo hợp đồng.

## 5. Bài sửa số 3 — Dùng bộ đếm ngoài để gán chỉ số

### 5.1. Sai: chỉ số phụ thuộc thứ tự scheduling

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> numbered = names.parallelStream()
        .map(name -> counter.getAndIncrement() + ":" + name)
        .toList();
~~~

Đây là mảnh mã với `names` kiểu `List<String>`. `AtomicInteger` bảo đảm phép tăng nguyên tử, nhưng **không bảo đảm tên nào nhận chỉ số nào** khi các callback chạy song song. `toList()` có thể giữ encounter order của phần tử đã được map, nhưng giá trị chỉ số gán trong callback có thể lộn với vị trí của phần tử.

Nếu chuyển sang `forEachOrdered`, bạn đang giải quyết **thứ tự thực thi action**, không nhất thiết biến mọi cách đọc/ghi state phụ thành thiết kế tốt.

### 5.2. Sửa: nguồn chỉ số là dữ liệu

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<String> numbered = IntStream.range(0, names.size())
        .parallel()
        .mapToObj(i -> i + ":" + names.get(i))
        .toList();

System.out.println(numbered);
~~~

Kết quả:

~~~text
[0:An, 1:Binh, 2:Chi]
~~~

Mỗi task nhận **chỉ số duy nhất từ nguồn**, không cần tranh chấp một bộ đếm toàn cục. Điều kiện: `names` phải ổn định trong lúc xử lý; cách `get(i)` phù hợp nhất với List hỗ trợ truy cập ngẫu nhiên hiệu quả (chẳng hạn `ArrayList` hoặc `List.of`). Với `LinkedList` lớn, truy cập lặp lại `get(i)` có thể kém hiệu quả; có thể chọn vòng lặp/iterator hoặc cách đánh số khác.

### 5.3. Trường hợp chỉ cần số lượng

Nếu mục tiêu là đếm:

~~~java
long count = names.parallelStream().count();
~~~

Không cần biến `counter`, cũng không cần tạo chuỗi đánh số. Trước khi sửa code, hãy xác định nghiệp vụ muốn **số lượng** hay **vị trí của từng phần tử**.

## 6. Bài sửa số 4 — Can thiệp nguồn khi duyệt

### 6.1. Sai: sửa chính danh sách đang được Stream duyệt

~~~java
List<String> source = new ArrayList<>(
        List.of("An", "Binh", "Chi"));

List<String> result = source.stream()
        .filter(name -> {
            if (name.startsWith("B")) {
                source.remove(name); // Sai: source interference.
            }
            return true;
        })
        .toList();
~~~

Đây là **mã sai về hợp đồng**, không phải ví dụ cần chạy để lấy stdout. `source` bị sửa trong lúc Stream đang traverse chính nó. Có thể xảy ra `ConcurrentModificationException` hoặc hành vi không được bảo đảm; không được giả định luôn phát hiện lỗi bằng exception.

### 6.2. Sửa: lọc khi tạo kết quả mới

~~~java
List<String> source = List.of("An", "Binh", "Chi");

List<String> result = source.stream()
        .filter(name -> !name.startsWith("B"))
        .toList();

System.out.println(source); // [An, Binh, Chi]
System.out.println(result); // [An, Chi]
~~~

Mục tiêu “loại phần tử khỏi kết quả” không bắt buộc phải xóa phần tử khỏi nguồn. Kết quả mới tránh tác dụng phụ và giúp kiểm thử rõ ràng.

Nếu bài toán thực sự cần xóa khỏi collection, có thể thực hiện **ở một bước ngoài Stream traversal**, ví dụ gọi `source.removeIf(predicate)` trên một List mutable trong một phase riêng, sau khi các pipeline dùng nguồn đã kết thúc. Không mutate nguồn đồng thời qua các task.

### 6.3. Source có mutable elements

Nguồn `List.of(...)` không thể thêm/xóa phần tử qua List API, nhưng nếu element là object mutable thì callback vẫn có thể sửa object ấy. Điều này có thể làm state quan sát được thay đổi hoặc race với callback khác. Hợp đồng non-interference và stateless vẫn cần xét tới **dữ liệu mà callback dùng**, không chỉ cấu trúc List.

## 7. Bài sửa số 5 — `reduce()` dùng phép trừ không kết hợp

### 7.1. Sai: hiểu reduction song song như vòng lặp từ trái sang phải

~~~java
int result = IntStream.of(10, 3, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

**Không dùng mã này để biểu diễn phép trừ lần lượt.** Phép trừ không kết hợp:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Khi Stream framework chia dãy và kết hợp kết quả theo các cách khác nhau, dùng phép trừ làm reduction operator vi phạm yêu cầu kết hợp và identity phù hợp. Một giá trị quan sát được ở một lần chạy **không** chứng minh được phép giảm này hợp lệ.

### 7.2. Khi thật sự muốn tổng rồi đổi dấu

Nếu nghiệp vụ là “tính âm của tổng”:

~~~java
int result = -IntStream.of(10, 3, 2)
        .parallel()
        .sum();

System.out.println(result); // -15
~~~

Đây là phép toán khác với biểu thức `10-3-2`: cần xác nhận ý nghĩa nghiệp vụ trước khi refactor. Không nên “sửa được parallel” bằng cách **thay đổi phép toán** mà không kiểm tra yêu cầu.

### 7.3. Khi muốn trừ từ trái sang phải

Nếu yêu cầu thực sự là `(10-3)-2=5`, thứ tự phép toán là một phần ngữ nghĩa; vòng lặp tuần tự với accumulator rõ ràng có thể dễ hiểu hơn:

~~~java
int[] values = {10, 3, 2};
int difference = values[0];

for (int i = 1; i < values.length; i++) {
    difference -= values[i];
}

System.out.println(difference); // 5
~~~

Đây là ví dụ đủ để minh họa phép trừ tuần tự. Với mảng rỗng cần quyết định chính sách riêng trước khi truy cập `values[0]`. Không dùng `reduce` không kết hợp chỉ để có cú pháp một dòng.

### 7.4. Có thể diễn đạt phép trừ bằng tổng các số mang dấu

Nếu bài toán là `a-b-c` và `a` được cho riêng, có thể tính:

~~~java
int first = 10;
int[] rest = {3, 2};
int difference = first - Arrays.stream(rest).sum();

System.out.println(difference); // 5
~~~

Đoạn code cần import `java.util.Arrays`. Trong miền số nguyên không overflow và với cách tách `first`/`rest` đúng, phép biến đổi này giữ kết quả toán học. Với phép tính có overflow hoặc quy tắc làm tròn, phải đánh giá ngữ nghĩa chi tiết thay vì mặc định mọi phép biến đổi đại số đều tương đương.

## 8. Bài sửa số 6 — Identity sai trong `reduce()`

### 8.1. Sai: dùng giá trị khởi đầu như identity

~~~java
int result = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(10, Integer::sum);
~~~

Nếu mong đợi `10 + (1+2+3+4) = 20`, đoạn này **không đúng về hợp đồng**. `10` không là identity của phép cộng. Trong parallel reduction, nhiều partial reductions có thể bắt đầu từ `10`, khiến giá trị này được góp vào nhiều lần.

### 8.2. Sửa: identity trung hòa rồi áp dụng “phí cố định” một lần

~~~java
int subtotal = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

int total = 10 + subtotal;
System.out.println(total); // 20
~~~

`0` trung hòa cho cộng. `10` là phần **nghiệp vụ cộng một lần**, được đặt sau reduction. Nếu khoản phí là giá trị riêng của từng phần tử thì công thức khác; cần phân biệt trước khi sửa.

### 8.3. Nhận diện những identity thông dụng

| Phép gộp | Identity phổ biến | Ghi chú |
| --- | --- | --- |
| `Integer::sum` | `0` | Cẩn thận overflow nếu cần tổng toán học |
| Nhân số nguyên | `1` | Không lấy `0` làm identity |
| `String::concat` | `""` | Thứ tự phần tử quan trọng |
| `Math::max` | Không có identity `int` tự nhiên cho mọi miền nếu không chọn min bound | Có thể dùng `max()` trả `OptionalInt` |
| `Math::min` | Không có identity `int` tự nhiên cho mọi miền nếu không chọn max bound | Có thể dùng `min()` trả `OptionalInt` |

Với `Math.max` trên `int`, `Integer.MIN_VALUE` có thể làm identity cho toàn miền int; với `Math.min`, `Integer.MAX_VALUE` có thể làm identity. Tuy nhiên, overload `max()`/`min()` trả Optional diễn đạt dữ liệu rỗng rõ ràng, thường thích hợp hơn việc tự gắn sentinel làm kết quả.

## 9. Bài sửa số 7 — Accumulator và combiner mâu thuẫn

### 9.1. Sai: cộng ở accumulator nhưng trừ ở combiner

~~~java
int result = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left - right);
~~~

Đoạn này có thể biên dịch nhưng **không thỏa hợp đồng**: accumulator đang xây các tổng cục bộ, combiner lại trừ các tổng nhánh. Kết quả phụ thuộc cách chia nhóm.

Với overload ba tham số:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Đây là chữ ký khái quát của `Stream.reduce`. Identity phải trung hòa với combiner; accumulator/combiner phải tương thích. Một luật khái niệm quan trọng là:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

Dấu `==` trong sơ đồ biểu thị **cùng giá trị theo ngữ nghĩa**, không bắt buộc bằng reference Java.

### 9.2. Sửa: cả hai cùng nghĩa tổng

~~~java
int result = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, Integer::sum, Integer::sum);

System.out.println(result); // 10
~~~

Với cùng kiểu input/output `Integer` và phép cộng, overload hai tham số `reduce(0,Integer::sum)` ngắn hơn. Nếu chỉ xử lý số nguyên, `mapToInt(Integer::intValue).sum()` cũng rõ mục đích.

### 9.3. Nếu hai bước có kiểu khác nhau?

Giả sử Stream chứa `Order` còn kết quả là `long`. Tùy bài toán, có thể dùng:

~~~java
long total = orders.stream()
        .mapToLong(Order::amount)
        .sum();
~~~

Đây là mảnh mã có `orders` kiểu `List<Order>` và `Order.amount()` trả long. Không cần vội dùng overload `reduce(identity, accumulator, combiner)` chỉ vì kiểu phần tử khác kiểu kết quả: mapping sang primitive stream có thể diễn đạt tính tổng đơn giản và giảm lỗi.

## 10. Bài sửa số 8 — Dùng mutable identity trong `reduce()`

### 10.1. Sai: tích lũy bằng một `StringBuilder` chung

~~~java
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                StringBuilder::append,
                StringBuilder::append);
~~~

Đây là **anti-pattern**: accumulator `append` thay đổi chính mutable identity. Trong parallel reduction, cùng identity object có thể tham gia nhiều nhánh không theo cách phù hợp với hợp đồng reduce. Việc mutate này cũng phá yêu cầu tương thích identity/combiner và có thể cho kết quả lặp hoặc sai.

**Không sửa bằng cách thêm `synchronized` lên StringBuilder rồi giữ nguyên `reduce`.** Vấn đề ở cả ngữ nghĩa reduction và cách dùng mutable identity.

### 10.2. Sửa trực tiếp: `Collectors.joining()`

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining());

System.out.println(text); // ABC
~~~

Nếu cần delimiter:

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining("|"));

System.out.println(text); // A|B|C
~~~

`Collectors.joining` là collector chuyên cho nối chuỗi; framework quản lý trạng thái tích lũy nội bộ và ghép theo hợp đồng. Với ordered Stream, nội dung trả về giữ encounter order của các phần tử.

### 10.3. Khi `reduce` thu giá trị immutable lại phù hợp

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", String::concat);

System.out.println(text); // ABC
~~~

`String` là immutable; mỗi phép concat tạo giá trị String tương ứng, và nối chuỗi là kết hợp theo nội dung. Tuy nhiên, số lượng object trung gian có thể lớn, nên `Collectors.joining` thường phù hợp hơn cho khối lượng chuỗi đáng kể.

### 10.4. `collect` với mutable container là một API khác

Không có nghĩa mọi accumulation mutable đều sai. `collect` được thiết kế riêng với supplier, accumulator, combiner và có thể phối hợp mutable container an toàn theo contract. Ví dụ:

~~~java
ArrayList<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Framework không yêu cầu bạn cung cấp **một `ArrayList` duy nhất dùng chung** cho mọi worker. Điều này khác với `reduce(new ArrayList<>(), ... mutate list...)`.

## 11. Bài sửa số 9 — Nhóm và đếm bằng `Map` bên ngoài

### 11.1. Sai: cập nhật `HashMap` từ nhiều callback

~~~java
Map<String, Integer> counts = new HashMap<>();

events.parallelStream().forEach(event -> {
    String key = event.category();
    counts.merge(key, 1, Integer::sum);
});
~~~

Đây là mẫu **không độc lập**: cần type `Event` có accessor `category()`, nguồn `events` và import `Map`, `HashMap`. `HashMap` thường không an toàn cho concurrent mutation. Dù `merge` có vẻ là một thao tác, đây không phải lời hứa nó an toàn khi nhiều thread cùng sửa một HashMap.

### 11.2. Sửa: `groupingBy` với downstream `counting`

~~~java
Map<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingBy(
                Event::category,
                Collectors.counting()));
~~~

Mỗi `count` là `Long`; việc tích lũy và kết hợp do framework điều phối. Nếu cần Map có thứ tự khóa để kiểm thử hay hiển thị:

~~~java
Map<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingBy(
                Event::category,
                TreeMap::new,
                Collectors.counting()));
~~~

`TreeMap` cho thứ tự khóa theo comparator/natural ordering phù hợp. Kết quả vẫn không mặc nhiên được phép cho nhiều thread đồng thời mutate mà không đồng bộ sau bước collect.

### 11.3. Khi đã có số nguyên làm khóa

~~~java
List<Integer> values = List.of(2, 3, 2, 5, 3);

Map<Integer, Long> histogram = values.parallelStream()
        .collect(Collectors.groupingBy(
                n -> n,
                TreeMap::new,
                Collectors.counting()));

System.out.println(histogram); // {2=2, 3=2, 5=1}
~~~

Đoạn minh họa này chạy trong Java 17 với import `List`, `Map`, `TreeMap`, `Collectors`. Không có mutable Map bên ngoài được callback trực tiếp sửa.

### 11.4. `groupingByConcurrent` khác hợp đồng

`groupingByConcurrent` là collector concurrent/unordered, có thể hữu ích khi không cần encounter order; nhưng không thay `groupingBy` vô điều kiện. Nếu downstream là List có thứ tự nhóm quan trọng, đọc rõ contract. Không dùng `ConcurrentHashMap` chỉ để che race trong một pipeline vốn có thể thu an toàn bằng collector.

## 12. Bài sửa số 10 — `peek` và side effect không đáng tin

### 12.1. Sai: dùng `peek` để thay đổi trạng thái nghiệp vụ

~~~java
List<String> names = List.of("A", "B", "C");
AtomicInteger observed = new AtomicInteger();

long count = names.stream()
        .peek(name -> observed.incrementAndGet())
        .count();
~~~

Không được kết luận `observed.get()` **phải bằng 3**. `peek` là intermediate operation thường dùng để quan sát/debug; Stream có thể tối ưu hóa bỏ qua việc thực thi một số giai đoạn nếu terminal result vẫn xác định được. `count()` trên nguồn có kích thước đã biết là ví dụ nơi callback trung gian có thể không cần được gọi.

Nếu cần đếm phần tử, `count` chính là phép đo. Nếu cần audit hoặc gọi dịch vụ bên ngoài, xác định phase riêng có retry/error/transaction và thứ tự rõ ràng; đừng giấu trong `peek`.

### 12.2. Quan sát để debug nhưng không phụ thuộc

~~~java
List<Integer> result = values.stream()
        .peek(n -> System.out.println("seen " + n))
        .map(n -> n * 2)
        .toList();
~~~

Đoạn này có `values` kiểu `List<Integer>` và chỉ nên dùng `peek` để quan sát tạm thời. Không viết logic mà tính đúng phụ thuộc mọi dòng `seen` luôn được in theo một thứ tự cố định ở mọi pipeline/implementation.

### 12.3. Một side effect hợp lệ vẫn cần thiết kế rõ

Có trường hợp terminal `forEach` được dùng để ghi file, gửi kết quả hoặc xuất log. Đây không mặc nhiên là lỗi, nhưng cần xác định:
- Ai sở hữu resource?
- Có cần encounter order?
- Callback có thể chạy đồng thời không?
- Xử lý exception và partial effects như thế nào?
- Có cần transaction, idempotency hoặc giới hạn số tác vụ không?

Một bước nghiệp vụ bắt buộc không nên chỉ dựa vào việc `peek` được gọi “như mong đợi”.

## 13. Chương trình Java 17 hoàn chỉnh: phiên bản đã sửa

Chương trình sau kiểm thử các quy tắc đã học **mà không cần chạy các anti-pattern gây race**. Đầu vào có phần tử trùng để kiểm tra histogram; pipeline chạy parallel ở những bước thích hợp; các kỳ vọng được kiểm tra bằng một helper ném `AssertionError` khi khác kết quả. Không dựa vào thứ tự callback hay thời gian chạy.

Tạo tệp **`PipelineRepairLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PipelineRepairLab {

    record Summary(long count, long sum) {}

    static void verify(String name, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + ": expected "
                    + expected + ", actual " + actual);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 3, 2, 5, 3);

        // Sửa shared accumulator: dùng reduce đúng.
        int sum = source.parallelStream()
                .reduce(0, Integer::sum);

        // Sửa map có side effect: tạo List mới.
        List<Integer> squares = source.parallelStream()
                .map(n -> n * n)
                .toList();

        // Sửa shared HashMap: groupingBy + counting.
        Map<Integer, Long> histogram = source.parallelStream()
                .collect(Collectors.groupingBy(
                        n -> n,
                        TreeMap::new,
                        Collectors.counting()));

        // Sửa AtomicInteger dùng làm chỉ số.
        List<String> indexed = IntStream.range(0, source.size())
                .mapToObj(i -> i + ":" + source.get(i))
                .toList();

        // Sửa mutable StringBuilder identity: joining.
        String joined = source.parallelStream()
                .map(String::valueOf)
                .collect(Collectors.joining("|"));

        // Cần mutable List kết quả? Chọn supplier rõ ràng.
        List<Integer> mutableCopy = source.parallelStream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutableCopy.add(99);

        // Nhiều chỉ tiêu trong một collect, không sửa state ngoài.
        Summary stats = source.parallelStream()
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Integer::longValue),
                        Summary::new));

        verify("sum", 15, sum);
        verify("squares",
                List.of(4, 9, 4, 25, 9), squares);
        verify("histogram",
                Map.of(2, 2L, 3, 2L, 5, 1L), histogram);
        verify("indexed",
                List.of("0:2", "1:3", "2:2", "3:5", "4:3"), indexed);
        verify("joined", "2|3|2|5|3", joined);
        verify("source unchanged",
                List.of(2, 3, 2, 5, 3), source);
        verify("stats", new Summary(5L, 15L), stats);

        System.out.println("sum=" + sum);
        System.out.println("squares=" + squares);
        System.out.println("histogram=" + histogram);
        System.out.println("indexed=" + indexed);
        System.out.println("joined=" + joined);
        System.out.println("mutableCopy=" + mutableCopy);
        System.out.println("source=" + source);
        System.out.println("stats=" + stats);
        System.out.println("checks=PASS");
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 PipelineRepairLab.java
java PipelineRepairLab
~~~

**Stdout chính xác:**

~~~text
sum=15
squares=[4, 9, 4, 25, 9]
histogram={2=2, 3=2, 5=1}
indexed=[0:2, 1:3, 2:2, 3:5, 4:3]
joined=2|3|2|5|3
mutableCopy=[2, 3, 2, 5, 3, 99]
source=[2, 3, 2, 5, 3]
stats=Summary[count=5, sum=15]
checks=PASS
~~~

### 13.1. Tại sao chương trình xác định được output dù có parallel?

Nguồn `List.of(2,3,2,5,3)` có encounter order và không bị sửa; phép cộng/đếm là reduction phù hợp; `toList` giữ encounter order; `joining` ghép theo thứ tự nguồn; `TreeMap` cho thứ tự key khi in histogram. Không có `System.out.println` trong callback song song.

### 13.2. Vì sao `mutableCopy` có 99 nhưng `source` không?

Collector `toCollection(ArrayList::new)` tạo kết quả mutable tách khỏi List nguồn. Sau collect, thêm 99 chỉ sửa `mutableCopy`. `source` vẫn có năm giá trị ban đầu, và `verify("source unchanged", ...)` kiểm chứng điều này.

### 13.3. Vì sao `stats` có hai field?

`Collectors.teeing` (có trong Java 12+) dùng hai downstream collectors: `counting()` và `summingLong(...)`, rồi merger `Summary::new` kết hợp hai kết quả thành một record. Nó diễn đạt yêu cầu đếm/tổng **bằng giá trị kết quả**, không bằng một mutable counter chung bên ngoài.

### 13.4. Vì sao histogram đúng?

Nguồn chứa `2` hai lần, `3` hai lần và `5` một lần. `groupingBy(...,TreeMap::new,counting())` thu đúng các lần xuất hiện; thứ tự khóa khi in là `2,3,5`. Không cần `HashMap.merge` trong callback `forEach` song song.

### 13.5. Vì sao `verify` hiệu quả hơn log các thread?

Nó kiểm tra giá trị và thứ tự mà API hứa, không giả định thread nào được gọi trước. Khi cần test tính đúng của parallel pipeline, hãy so sánh kết quả với bộ kỳ vọng và xét các invariant về source/loại kết quả, chứ không dựa vào output log hoặc kết quả một lần race.

## 14. Viết bài kiểm thử tốt hơn: những ca biên

### 14.1. Nguồn rỗng

~~~java
List<Integer> empty = List.of();

int sum = empty.stream().reduce(0, Integer::sum);
long count = empty.stream().count();
List<Integer> result = empty.stream().toList();

System.out.println(sum);    // 0
System.out.println(count);  // 0
System.out.println(result); // []
~~~

Identity phải hợp lệ với trường hợp không có phần tử. `max()`/`min()` thường trả `Optional` vì không có giá trị cực trị của tập rỗng; đừng tự chọn một sentinel khiến “không có dữ liệu” bị hiểu thành dữ liệu thật.

### 14.2. Dữ liệu có phần tử trùng

Nguồn `[2,3,2,5,3]` có duplicate để thử histogram. Nếu bài toán cần giữ bản ghi trùng, không thêm `distinct()` tùy tiện: nó thay đổi semantics, làm số lượng giảm và giá trị tổng có thể khác.

### 14.3. Dữ liệu số âm và 0

~~~java
List<Integer> values = List.of(-2, 0, 3);
int sum = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 1
~~~

Test này hữu ích để phát hiện code vô tình chỉ đúng với dữ liệu dương, hoặc dùng identity không phù hợp.

### 14.4. Overflow

~~~java
int wrapped = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(wrapped); // -2147483648
~~~

Đây là số học `int` Java bị overflow; phép cộng modulo vẫn có tính kết hợp theo bit-pattern, nhưng kết quả **không phải tổng toán học dự định**. Nếu domain không cho phép overflow, dùng kiểu rộng hơn:

~~~java
long exactForTheseInputs =
        IntStream.of(Integer.MAX_VALUE, 1)
                .mapToLong(n -> n)
                .sum();

System.out.println(exactForTheseInputs); // 2147483648
~~~

Với dữ liệu rộng hơn cả `long`, cần kiểm soát miền hoặc dùng `BigInteger` khi thích hợp. `Math.addExact` giúp phát hiện overflow trong phạm vi nhất định nhưng khi sử dụng với parallel reduction và nhiều nhánh, thứ tự phát hiện exception có thể khác; tính đúng cần dựa trên chính sách miền dữ liệu.

### 14.5. Số thực và sai số làm tròn

`double` có phép cộng theo floating point nên về mặt bitwise có thể không kết hợp:

~~~text
a = 1.0e16
b = -1.0e16
c = 1.0

(a + b) + c = 1.0
a + (b + c) = 0.0
~~~

Thay đổi cách chia nhóm có thể ảnh hưởng sai số. Không khẳng định mọi parallel `DoubleStream.sum()` hay custom reduce sẽ luôn có kết quả bitwise giống sequential trong mọi workload. Nếu nghiệp vụ cần tổng tiền hoặc độ chính xác/lặp lại cao, chọn kiểu số và phương pháp tích lũy đáp ứng yêu cầu, ví dụ `BigDecimal` với scale/rounding rõ hoặc thuật toán tính tổng số thực có kiểm soát sai số.

### 14.6. Không dựa vào thất bại ngẫu nhiên của mã sai

Một race condition có thể không xuất hiện trong lần test duy nhất; race detector hoặc các test lặp có thể hỗ trợ điều tra, nhưng cách sửa đúng cần dựa trên contract và cấu trúc callback. Ngược lại, những anti-pattern như dùng `reduce(10,Integer::sum)` có thể cho kết quả đúng khi chạy tuần tự một vài trường hợp, nhưng vẫn vi phạm identity cho reduction tổng quát.

### 14.7. So sánh sequential và parallel cần có điều kiện

Có thể đặt test:

~~~java
int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

if (sequential != parallel) {
    throw new AssertionError("inconsistent sum");
}
~~~

Đây là mảnh mã có `values` kiểu `List<Integer>`. Với phép cộng `int` thuần, identity đúng, nguồn ổn định và không có side effect, giá trị phải phù hợp ngữ nghĩa cộng Java. Nhưng **chỉ so sánh hai output bằng nhau chưa chứng minh mọi luật reduction**: một phép sai có thể tình cờ cho cùng kết quả trên một input. Cần kiểm tra cả tính kết hợp, identity và compatibility.

## 15. Thực hành review: đọc mã rồi chọn sửa hay giữ tuần tự

### Tình huống A — Nối tên thành CSV

Mã sai:

~~~java
StringBuilder csv = new StringBuilder();

names.parallelStream()
        .forEach(name -> csv.append(name).append(","));
~~~

Vì `StringBuilder` không thread-safe, callback cùng mutate một object; thứ tự ghép cũng không được `forEach` bảo đảm. Nếu muốn delimiter đúng giữa các tên:

~~~java
String csv = names.stream()
        .collect(Collectors.joining(","));
~~~

Khi tên có thể chứa dấu phẩy, dấu nháy hoặc xuống dòng, việc tạo CSV thật cần escaping/quoting đúng format; `joining(",")` chỉ minh họa cách nối chuỗi bằng delimiter.

### Tình huống B — Gọi dịch vụ từ mỗi phần tử

~~~java
requests.parallelStream()
        .forEach(api::send);
~~~

Không thể kết luận “an toàn” hay “sai” chỉ từ cú pháp. Cần biết `api.send` có thread-safe không, số request đồng thời, rate limit, timeout, thứ tự yêu cầu, retry và idempotency. Nếu là side effect nghiệp vụ bắt buộc, thường cần cơ chế concurrency được kiểm soát thay vì mặc định parallel Stream và hy vọng.

### Tình huống C — Phụ thuộc thứ tự in

~~~java
values.parallelStream().forEach(System.out::println);
~~~

Đầu ra có thể xuất hiện lộn thứ tự. Nếu phải theo encounter order:

~~~java
values.parallelStream().forEachOrdered(System.out::println);
~~~

`forEachOrdered` đảm bảo thứ tự action của ordered Stream, nhưng vẫn có thể giới hạn hiệu năng và **không sửa mọi race** trong mã callback. Để kiểm thử dữ liệu, thu `toList()` rồi so sánh List thường đơn giản hơn.

### Tình huống D — Cập nhật database trong `map`

~~~java
List<Result> results = records.parallelStream()
        .map(record -> repository.save(record))
        .toList();
~~~

Đây là **mẫu thiết kế cần xem xét**, không khẳng định an toàn. `repository.save` có side effect I/O và có thể có transaction, connection pool và lỗi giữa chừng. Nếu muốn pipeline được coi là pure transformation thì `map` này không thuần. Tách bước tính kết quả và bước persistence khi phù hợp; nếu xử lý song song I/O, quản lý explicit concurrency, retries và transaction.

## 16. Bài tập tự làm

### Bài 1 — Refactor List chung

Đầu vào `IntStream.range(0,1000)`. Code dùng `parallel().forEach(shared::add)`. Sửa thành `boxed().toList()`, kiểm tra số lượng/thứ tự; sau đó sửa thêm phiên bản cần mutable `ArrayList` bằng `toCollection(ArrayList::new)`.

### Bài 2 — Mảng tổng chung

Dùng `int[] holder={0}` và cập nhật trong `parallel().forEach` để cộng 1..1000. Phân tích race, rồi viết `sum()` và `reduce(0,Integer::sum)`. Viết test kỳ vọng 500500 và thử chuyển `mapToLong` khi miền tổng có thể vượt `int`.

### Bài 3 — Đánh số bằng AtomicInteger

Tạo List `["An","Binh","Chi"]`. Viết phiên bản dùng `AtomicInteger.getAndIncrement` trong `parallel().map`, giải thích vì sao nhãn/chỉ số không có bảo đảm tương ứng vị trí; sửa bằng `IntStream.range(0,size).mapToObj(i -> i+":"+list.get(i))`.

### Bài 4 — Không can thiệp source

Cho ArrayList `["A","B","C"]`; pipeline xóa phần tử B trong `filter`. Viết lại thành `filter(name -> !name.equals("B"))` và thu List mới. Test xác nhận source vẫn nguyên `["A","B","C"]`.

### Bài 5 — Phép trừ và associativity

Tính `(10-3)-2` và `10-(3-2)`. Giải thích vì sao hai kết quả khác nhau. Chọn vòng lặp tuần tự cho “trừ trái sang phải”, hoặc `first - sum(rest)` khi đúng đại số và miền số; không đưa phép trừ vào parallel reduce tùy tiện.

### Bài 6 — Identity khác giá trị phí cố định

Code dùng `reduce(10,Integer::sum)` để “thêm phí 10” vào tổng 1..4. Sửa bằng `reduce(0,Integer::sum)` rồi cộng 10 một lần; giải thích vì sao parallel split làm identity 10 sai.

### Bài 7 — Combiner tương thích

Cho `reduce(0,Integer::sum,(a,b)->a-b)`. Chỉ ra vấn đề và sửa combiner thành `Integer::sum`. Trình bày luật tương thích khi accumulator và combiner có kiểu khác nhau.

### Bài 8 — Mutable StringBuilder

Cho `Stream.of("A","B","C").parallel().reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)`. Giải thích vì sao mutable identity vi phạm hợp đồng; sửa bằng `collect(Collectors.joining())` và `joining("|")`. So sánh với `reduce("",String::concat)`.

### Bài 9 — Đếm theo khóa

Cho `List.of(2,3,2,5,3)`; viết histogram `{2=2,3=2,5=1}` bằng `groupingBy(n->n,TreeMap::new,counting())`. Không dùng HashMap chung trong `parallel().forEach`. Thử nguồn rỗng và giải thích Map kết quả.

### Bài 10 — `peek` và tối ưu hóa

Dùng `List.of(1,2,3).stream().peek(...).count()`. Giải thích vì sao không nên kiểm thử chính sách đếm bằng số lần `peek` được gọi. Sửa bằng `count` hoặc `collect` phù hợp.

### Bài 11 — Tạo Summary không có shared state

Dùng `Collectors.teeing(Collectors.counting(),Collectors.summingLong(Integer::longValue),Summary::new)` với `record Summary(long count,long sum)`. Test `Summary(5,15)` cho `[2,3,2,5,3]`. So sánh với hai biến global `count`/`sum`.

### Bài 12 — Viết test theo bất biến

Cho một pipeline song song của dự án, liệt kê những kỳ vọng có thể assert: nguồn không đổi, số lượng phần tử, tập phần tử, thứ tự nếu có encounter order, tổng/group theo yêu cầu, không làm rò reference mutable. Thêm ca rỗng, duplicate, số âm và overflow. Không coi việc “chạy 100 lần không lỗi” là bằng chứng tuyệt đối.

## 17. Checklist nghiệm thu một pipeline đã sửa

1. Đề bài nghiệp vụ là **giữ thứ tự, đếm, tính tổng, phân nhóm hay cập nhật bên ngoài**? Có chọn đúng phép toán?
2. Behavioral parameters có mutate source đang duyệt không?
3. Lambda có đọc/ghi trạng thái mutable bên ngoài theo thời gian không?
4. Nếu có `AtomicInteger`/synchronized collection, nó có đang che một cách tích lũy stateful không cần thiết không?
5. Với `reduce`, phép gộp có **kết hợp** không?
6. Identity có trung hòa đúng cho cả reduction tuần tự lẫn song song không?
7. Với overload ba tham số, accumulator/combiner có tương thích theo semantics không?
8. Có dùng mutable identity trong `reduce` không? Có nên chuyển sang `collect`?
9. Có đang dùng `parallel().forEach` để tích lũy vào List/Map chung không?
10. Loại collection sau collect có đúng yêu cầu mutable/unmodifiable không?
11. `Collectors.toList()` có đang bị suy diễn là luôn `ArrayList` mutable không?
12. Nguồn có encounter order không? Nếu cần thứ tự, terminal operation có giữ đúng không?
13. Có đang dựa vào số lần `peek`/`map` chạy để làm side effect nghiệp vụ không?
14. Có làm thay đổi ngữ nghĩa khi refactor phép trừ sang phép tổng hoặc thay đổi identity không?
15. Dữ liệu lớn có gây overflow, tiêu tốn bộ nhớ hoặc chi phí parallel overhead không?
16. Unit test có ca rỗng, duplicate, negative, boundary và so sánh sequential/parallel khi hợp lệ không?
17. Mã được sửa đã được biên dịch Java 17 và kiểm tra stdout đúng với hợp đồng chưa?
18. Nếu pipeline thực hiện I/O, transaction, API call, logging hoặc email, đã có chính sách retry, failure, giới hạn concurrency và idempotency phù hợp chưa?

## 18. Tổng kết và tài liệu tham khảo

**Sửa pipeline dùng trạng thái bên ngoài** thường là chuyển từ `forEach(shared::add)`, mảng tổng dùng chung hay counter cạnh tranh sang **`map`/`filter` thuần và `collect`/`reduce` đúng hợp đồng**. Với thứ tự phần tử, ưu tiên nhận chỉ số từ dữ liệu hoặc thu List thay vì dựa vào thứ tự scheduling. Không mutate nguồn đang Stream duyệt.

**Sửa `reduce()` sai** đòi hiểu chính xác đại số của phép gộp: associativity, identity và tương thích accumulator/combiner. Không dùng phép trừ không kết hợp, không lấy giá trị “phí khởi tạo” làm identity và không mutate một StringBuilder/List dùng làm identity cho `reduce`. Dùng `sum`, `count`, `max`, `joining`, `groupingBy`, `toCollection` hoặc `teeing` khi chúng mô tả trực tiếp bài toán.

Cuối cùng, **kiểm thử bằng hợp đồng**, không bằng may mắn của race. Kiểm tra kết quả, nguồn bất biến, order khi có cam kết, dữ liệu rỗng, phần tử trùng và các ranh giới số học. Parallel Stream là một cách thực thi; tính đúng phải có trước khi tối ưu.

Tài liệu chính thức: Javadoc Java SE 17 của `java.util.stream.Stream` (đặc biệt `reduce`, `collect`, `forEach`, `forEachOrdered`, `peek`), `IntStream`, `java.util.stream.Collectors` (`joining`, `groupingBy`, `counting`, `toCollection`, `teeing`) và Java Stream package documentation về *Non-interference*, *Stateless behaviors*, *Reduction*, *Side-effects* và *Ordering*.
