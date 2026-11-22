# Identity, associativity và thứ tự cập nhật không xác định trong tích lũy Java 8+

Một phép tích lũy (accumulation) kết hợp nhiều phần tử thành một kết quả: tính tổng, đếm, tìm min/max, gộp danh sách, xây bản đồ tần suất, nối chuỗi hoặc gom đối tượng theo nhóm. Khi chuyển từ một vòng lặp tuần tự sang `Stream.reduce`, `Stream.collect` hoặc `parallelStream()`, ba khái niệm là nền tảng của tính đúng đắn:

1. **Identity (phần tử đơn vị):** giá trị bắt đầu phải không làm thay đổi kết quả của phép gộp, kể cả khi được áp dụng cho từng nhánh song song.
2. **Associativity (tính kết hợp):** thay đổi cách đặt ngoặc/gộp kết quả từng phần không được đổi kết quả hợp lệ.
3. **Thứ tự cập nhật (update/execution order):** một stream có thứ tự gặp phần tử (**encounter order**) không có nghĩa callback sẽ thực thi hoặc cập nhật trạng thái theo đúng thứ tự đó, đặc biệt trong pipeline song song.

Trong Java 8, các thao tác `reduce` và `collect` thiết kế để có thể chia nguồn thành nhiều phân đoạn, tính kết quả cục bộ rồi gộp lại; tính đúng đắn phụ thuộc vào **hợp đồng toán học và trạng thái** của hàm do người lập trình cung cấp. Điều này vẫn đúng trên JDK hiện đại. Hầu hết API minh họa có từ Java 8; chương trình đầy đủ ở cuối bài biên dịch được với JDK 17+ bằng `javac --release 17`.

**Hợp đồng nghiệp vụ trước tốc độ:** nếu cần trả đúng tổng, tập kết quả, thứ tự hiển thị, hay bản ghi mới nhất thì phải nói rõ kiểu kết quả và yêu cầu về thứ tự. `parallel()` không phải nút tự động tăng tốc cho một phép tính đang dựa vào biến tích lũy dùng chung.

## 1. Tích lũy tuần tự và song song khác ở đâu?

Một vòng lặp tuần tự có thứ tự cập nhật hiển nhiên:

~~~java
int sum = 0;
for (int number : Arrays.asList(1, 2, 3, 4)) {
    sum += number;
}
// sum = 10.
~~~

Đổi sang `Stream.reduce`:

~~~java
int sum = Arrays.asList(1, 2, 3, 4).stream()
    .reduce(0, Integer::sum);
// 10.
~~~

Nếu chạy song song:

~~~java
int sum = Arrays.asList(1, 2, 3, 4).parallelStream()
    .reduce(0, Integer::sum);
// Vẫn là 10 khi phép toán đáp ứng đúng hợp đồng.
~~~

**Mô hình suy nghĩ** với dữ liệu `[1, 2, 3, 4]`:

~~~text
Tuần tự:  (((0 + 1) + 2) + 3) + 4 = 10

Một cách chia hợp lệ:
  nhóm A = 0 + 1 + 2 = 3
  nhóm B = 0 + 3 + 4 = 7
  kết quả = 3 + 7 = 10

Một cách chia khác:
  nhóm A = 0 + 1 = 1
  nhóm B = 0 + 2 + 3 = 5
  nhóm C = 0 + 4 = 4
  kết quả = (1 + 5) + 4 = 10
~~~

Đây là *mô hình minh họa phép chia*, không phải lời hứa JVM sẽ tạo đúng các nhánh như trên. Việc tách, lên lịch và gộp là chi tiết được phép thay đổi. Identity đúng và phép gộp có tính kết hợp giúp **kết quả cuối cùng không phụ thuộc hình dạng cây gộp**.

## 2. Identity: giá trị khởi tạo phải là phần tử đơn vị

Với toán tử gộp nhị phân `op`, identity `e` phải thỏa điều kiện trên các giá trị hợp lệ:

~~~text
op(e, x) = x
op(x, e) = x
~~~

Để nói một phép toán có **phần tử đơn vị hai phía**, cả hai vế đều cần đúng. Với `Stream.reduce(identity, accumulator)`, Javadoc đặc biệt yêu cầu identity thỏa `accumulator.apply(identity, t).equals(t)`; khi tách và gộp song song, điều quan trọng là identity tương thích với toàn bộ phép toán và mỗi nhánh.

| Phép toán | Identity đúng | Vì sao |
| --- | --- | --- |
| Cộng các số nguyên | `0` | `0 + x = x + 0 = x` |
| Nhân các số | `1` | `1 × x = x × 1 = x` |
| Nối chuỗi | `""` | `"" + s = s + "" = s` |
| Ghép danh sách theo concat | Danh sách trống mới | Ghép rỗng không thêm phần tử |
| Hợp tập hợp | Tập rỗng | Hợp với rỗng không đổi tập |
| Toán tử OR boolean | `false` | `false || x = x` |
| Toán tử AND boolean | `true` | `true && x = x` |
| Lấy min | Cận trên phù hợp domain, hoặc không dùng identity | Identity phải không thay kết quả |
| Lấy max | Cận dưới phù hợp domain, hoặc không dùng identity | Identity phải không thay kết quả |

**Min/max cần cẩn trọng:** với miền `int` đầy đủ, `Integer.MAX_VALUE` có thể là identity của `Math::min` và `Integer.MIN_VALUE` có thể là identity của `Math::max`. Nhưng nếu cần phân biệt stream trống với stream có giá trị đúng tại cận đó, dùng `min(Comparator)`, `max(Comparator)` hoặc `reduce(BinaryOperator)` trả `Optional` thay vì một giá trị sentinel giả.

Các stream rỗng làm lộ đặc tính của identity:

~~~java
int zero = Stream.<Integer>empty().reduce(0, Integer::sum);
// zero = 0.

Optional<Integer> none = Stream.<Integer>empty().reduce(Integer::sum);
// none.isPresent() = false.
~~~

`reduce(identity, op)` luôn có một giá trị kiểu `T` (dù đầu vào rỗng); `reduce(op)` không có identity explicit và trả `Optional<T>` để thể hiện không có phần tử. Đừng nhận `0` từ stream rỗng rồi luôn suy ra dữ liệu thật đã chứa số 0.

### Phản ví dụ: dùng identity 100 cho phép cộng

~~~java
int wrongSequential = Stream.of(1, 2, 3)
    .reduce(100, Integer::sum);
// 106 theo cách gộp tuần tự đơn giản.
~~~

Nhưng identity `100` không phải đơn vị của phép cộng. Nếu input được chia thành hai phần `[1]` và `[2,3]` rồi mỗi phần khởi đầu ở 100:

~~~text
Nhóm A = 100 + 1 = 101
Nhóm B = 100 + 2 + 3 = 105
Gộp    = 101 + 105 = 206
Tuần tự = 100 + 1 + 2 + 3 = 106
~~~

**Kết quả thực của một lần `parallelStream().reduce(100,Integer::sum)` không được bảo đảm là 206**; bài này chỉ chứng minh identity sai khiến những cách phân hoạch khác nhau có thể trả khác nhau. Đừng giải thích rằng mỗi stream song song “chắc chắn cộng 100 hai lần”: số phân đoạn và cây gộp tùy triển khai.

## 3. Associativity: có thể đổi cách nhóm mà không đổi đáp án

Một toán tử `op` có tính kết hợp khi:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

Ví dụ cộng số nguyên trong miền **không tràn**:

~~~text
(10 + 3) + 2 = 10 + (3 + 2) = 15
~~~

Nhân số, min/max và nối chuỗi đều là những phép toán kết hợp theo semantics phù hợp. **Tính kết hợp không đồng nghĩa với giao hoán**.

### Phản ví dụ: phép trừ

~~~java
int leftGrouping = (10 - 3) - 2; // 5.
int rightGrouping = 10 - (3 - 2); // 9.
~~~

Vì `5 != 9`, phép trừ **không có tính kết hợp**. Dùng:

~~~java
int result = Stream.of(10, 3, 2)
    .parallel()
    .reduce(0, (a, b) -> a - b); // SAI HỢP ĐỒNG reduce.
~~~

không có nghĩa Java hứa một kết quả chính xác. Nếu nghiệp vụ là “trừ tất cả số thứ hai trở đi khỏi số thứ nhất”, có thể xử lý tuần tự hoặc chuyển thành mô hình tổng có dấu rõ ràng (ví dụ lấy phần tử đầu, rồi trừ tổng phần còn lại) sau khi định nghĩa cả trường hợp stream trống.

### Tính kết hợp khác giao hoán

Nối chuỗi:

~~~text
("a" + "b") + "c" = "a" + ("b" + "c") = "abc"
"a" + "b" != "b" + "a"
~~~

Nối chuỗi **kết hợp** nhưng **không giao hoán**. Nếu stream **có encounter order**, reduction hợp lệ có thể vẫn trả theo thứ tự phần tử đó dù phần việc được tính song song. Ví dụ:

~~~java
String s = Stream.of("a", "b", "c")
        .parallel()
        .reduce("", String::concat);
// "abc" với nguồn có encounter order.
~~~

Không cần giả định phép gộp phải giao hoán cho mọi phép reduce song song; điều kiện về encounter order và `UNORDERED` quyết định có thể đảo thứ tự phần tử hay không.

## 4. Associativity toán học và số thực dấu phẩy động

Phép cộng các số `double` có thể **không kết hợp tuyệt đối** ở mức bit, vì mỗi lần cộng có làm tròn nhị phân:

~~~java
double left = (1e16 + -1e16) + 1.0;   // 1.0.
double right = 1e16 + (-1e16 + 1.0);  // 0.0.
~~~

Trong phép tính thứ hai, `-1e16 + 1.0` bị làm tròn còn gần `-1e16`, nên khi cộng tiếp `1e16` cho 0. Đây là khác biệt có thể tồn tại khi tổng nhiều số được nhóm theo thứ tự khác, kể cả không có data race.

Nếu báo cáo yêu cầu **đúng tuyệt đối theo số thập phân**, cân nhắc `BigDecimal` với cách tạo giá trị và scale rõ. `BigDecimal.add` **không truyền `MathContext` để làm tròn trung gian** thực hiện cộng thập phân chính xác; khi dùng context có làm tròn ở từng phép toán, tính kết hợp thực tế vẫn có thể bị ảnh hưởng bởi precision/rounding. Nếu tổng có thể vượt `int`/`long`, dùng kiểu/chiến lược kiểm tra tràn phù hợp.

Đừng coi “parallel cho tổng double lệch vài ulp” là lỗi JVM mà tự thay đổi thứ tự callback để đạt một kết quả quan sát ngẫu nhiên. Hãy xác định tolerance, phương pháp tổng và yêu cầu độ chính xác theo domain.

## 5. Ba dạng `Stream.reduce` cần phân biệt

`Stream<T>` cung cấp ba nhóm overload liên quan:

| Dạng | Kiểu trả về | Điều kiện chủ chốt |
| --- | --- | --- |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Accumulator kết hợp, không can thiệp nguồn |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Identity đúng; accumulator kết hợp, stateless |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Identity của combiner; combiner kết hợp và tương thích accumulator |

Tất cả đều là **terminal operation**, tiêu thụ stream; không thể tái sử dụng cùng stream instance sau terminal.

### 5.1. Dạng một: không có identity explicit

~~~java
Optional<Integer> result = Stream.of(4, 8, 2)
        .reduce(Integer::sum);
// Optional[14].

Optional<Integer> empty = Stream.<Integer>empty()
        .reduce(Integer::sum);
// Optional.empty.
~~~

Đây là lựa chọn tốt khi kết quả của tập rỗng có ý nghĩa là **không tồn tại** chứ không phải giá trị 0.

### 5.2. Dạng hai: cùng kiểu dữ liệu

~~~java
int total = Stream.of(4, 8, 2)
        .reduce(0, Integer::sum);
// 14.

int product = Stream.of(4, 8, 2)
        .reduce(1, (a, b) -> a * b);
// 64.
~~~

Tổng hay tích có tính kết hợp trong phạm vi arithmetic được mô hình hóa. Không dùng `reduce(new ArrayList<>(), ...)` với phép sửa list trong lambda để xây một danh sách vì `reduce` này dùng identity kiểu value và có thể chia/gộp.

### 5.3. Dạng ba: accumulator khác kiểu phần tử

~~~java
List<String> words = Arrays.asList("java", "stream", "api");

int totalCharacters = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        Integer::sum);
// 13.
~~~

Đây là `Stream<String>` nhưng kết quả `U` là `Integer`. Accumulator đưa một phần tử mới vào tổng; combiner gộp hai tổng từng phần. Điều kiện tương thích của API (giải thích ở mục tiếp theo) bảo đảm chia nguồn không làm sai kết quả.

Ở tình huống đơn giản này, cách đọc dễ hơn thường là:

~~~java
int totalCharacters = words.parallelStream()
        .mapToInt(String::length)
        .sum();
// 13.
~~~

Dùng ba đối số khi việc gộp mapping và reduction có lợi ích cụ thể hoặc logic domain thật sự yêu cầu; không mặc định nó “luôn nhanh hơn”.

## 6. Ba đối số `reduce(identity, accumulator, combiner)`: hợp đồng tương thích

Với kiểu kết quả `U`, phần tử nguồn `T`, Java yêu cầu:

~~~text
combiner(identity, u) = u

combiner(combiner(a, b), c)
    = combiner(a, combiner(b, c))

combiner(u, accumulator(identity, t))
    = accumulator(u, t)
~~~

Điều cuối là **tương thích giữa combiner và accumulator**. Nếu các nhánh dùng accumulator để tính tổng cục bộ rồi combiner dùng phép toán khác, kết quả có thể sai ngay cả khi từng hàm riêng lẻ trông có vẻ hợp lý.

Ví dụ đúng với bài toán tổng độ dài chuỗi:

~~~java
int totalLength = words.parallelStream().reduce(
    0,
    (subtotal, word) -> subtotal + word.length(),
    Integer::sum);
~~~

Kiểm tra giả sử `u = 7`, `t = "java"`:

~~~text
accumulator(identity=0, "java") = 4
combiner(7, 4) = 11

accumulator(7, "java") = 11
=> Hai vế tương thích.
~~~

**Sai lầm thường gặp:** nhánh accumulator tăng `subtotal + word.length()`, nhưng combiner lại nhân hai kết quả. Dù phép nhân có tính kết hợp và identity 1, nó **không tương thích** với accumulator được thiết kế để cộng độ dài; kết quả khi song song tách nhánh khác kết quả tuần tự.

Phần tử identity còn cần có ngữ nghĩa đúng với việc tích lũy một phần tử đầu tiên:

~~~java
// ĐÚNG: identity = 0, combiner = cộng.
int chars = words.parallelStream().reduce(
    0, (sum, w) -> sum + w.length(), Integer::sum);

// SAI: identity = 1, combiner = cộng, vì 1 không là identity.
int wrong = words.parallelStream().reduce(
    1, (sum, w) -> sum + w.length(), Integer::sum);
~~~

Biến `wrong` là **phản ví dụ**, không sử dụng làm kết quả nghiệp vụ; JVM không cam kết nó có giá trị nào giống kết quả tuần tự vì đã vi phạm hợp đồng.

### Accumulator phải không can thiệp nguồn và không giữ state biến thiên

Ngoài công thức toán học, các hàm dùng cho Stream phải **non-interfering** (không sửa source dữ liệu đang được duyệt, trừ khi nguồn được thiết kế đặc biệt cho concurrent modification) và **stateless** (không dựa vào trạng thái biến thiên từ bên ngoài). Ví dụ:

~~~java
int sum = numbers.parallelStream()
    .reduce(0, Integer::sum);
~~~

thỏa mục tiêu hơn:

~~~java
// KHÔNG DÙNG: accumulator có side effect trên shared state.
AtomicInteger counter = new AtomicInteger();
int sum = numbers.parallelStream()
    .reduce(0, (partial, x) -> {
        counter.incrementAndGet();
        return partial + x;
    }, Integer::sum);
~~~

Ngay cả khi `AtomicInteger` tránh lost-update cho biến đếm, code vẫn phụ thuộc side effect không thuộc hợp đồng kết quả reduction; một số pipeline có thể tối ưu bỏ callback, và thứ tự/luồng thực thi không được bảo đảm. Nếu cần kết quả phép tính, hãy **trả qua reduction**; nếu cần metric độc lập, thiết kế observability đúng scope và concurrency.

## 7. Mutable reduction: `collect` khác `reduce`

`reduce` là phép gộp **theo giá trị**: mỗi bước sinh một giá trị `U` mới hoặc bất biến về mặt ngữ nghĩa. `collect` dành cho **tích lũy mutable**: sử dụng một container như `ArrayList`, `HashMap`, thống kê mutable riêng; đưa phần tử vào container rồi gộp các container cục bộ.

Ba đối số của `Stream.collect`:

~~~java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner)
~~~

Đây là chữ ký khái niệm; trong khai báo generic chính xác của `Stream`, `R` cũng nằm trong kiểu trả về method.

Ba vai trò:

- **`supplier`:** tạo một container trống **mới** cho từng nhóm kết quả khi cần.
- **`accumulator`:** thêm một phần tử `T` vào container `R`.
- **`combiner`:** gộp phần tử từ container thứ hai vào container thứ nhất.

Ví dụ đúng:

~~~java
List<String> values = Arrays.asList("java", "stream", "api");

List<String> result = values.parallelStream().collect(
    ArrayList::new,
    ArrayList::add,
    ArrayList::addAll);
// [java, stream, api] với nguồn List có encounter order.
~~~

`collect` có thể phân chia source, cung cấp các `ArrayList` cục bộ, thêm phần tử rồi gộp mà **không cần nhiều thread cùng sửa một list chung**. Đây là lý do `ArrayList` không thread-safe vẫn có thể là container hợp lệ của collector **không concurrent**, miễn implementation giữ thread confinement theo hợp đồng Collector.

### Vì sao không dùng mutable identity với `reduce`?

**Phản ví dụ cần tránh:**

~~~java
List<String> identity = new ArrayList<>();

List<String> wrong = values.parallelStream().reduce(
    identity,
    (acc, word) -> {
        acc.add(word);
        return acc;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    });
~~~

Đoạn này có thể biên dịch nhưng **sai hợp đồng reduction**: identity là một instance mutable **dùng chung làm giá trị đầu vào** cho các phép tích lũy; lambda thay đổi object đó. Trong parallel reduction, việc chia/gộp có thể dẫn đến cùng danh sách bị sửa từ nhiều nhánh, phần tử bị nhân bản hoặc kết quả không ổn định. Không chạy mẫu này để lấy stdout như một “hành vi được bảo đảm”.

Dùng `collect` hoặc một `Collector` chuẩn thay thế:

~~~java
List<String> safe = values.parallelStream()
        .collect(Collectors.toList());
// Giữ encounter order khi stream có thứ tự.
~~~

**Lưu ý về `Collectors.toList()`:** tài liệu không hứa kiểu List cụ thể, khả năng chỉnh sửa hoặc tính thread-safe của **kết quả**. Nếu cần container xác định là `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. `Stream.toList()` có từ Java 16, trả List unmodifiable, không nên nhầm với `Collectors.toList()` khi bài học dùng API Java 8.

## 8. Hợp đồng identity và associativity của `Collector`

Một `Collector<T, A, R>` mô tả bốn chức năng:

~~~text
supplier:    () -> A          tạo accumulator container
accumulator: (A, T) -> void   đưa phần tử vào container
combiner:    (A, A) -> A      hợp hai container
finisher:    A -> R           kết quả cuối (có thể identity)
~~~

Ngoài ra có `Characteristics` như `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`. Các **luật** quan trọng:

**Luật identity:** với accumulator từng phần `a`, gộp với một container **trống mới** phải cho kết quả **tương đương**:

~~~text
a ≡ combiner(a, supplier())
~~~

**Luật associativity:** kết quả khi xử lý tuần tự toàn bộ phần tử và kết quả khi chia thành các nhánh, tích lũy rồi gộp các container phải tương đương:

~~~text
a1 = supplier()
accumulate(a1, t1)
accumulate(a1, t2)
r1 = finish(a1)

a2 = supplier()
accumulate(a2, t1)

a3 = supplier()
accumulate(a3, t2)

r2 = finish(combine(a2, a3))

=> r1 ≡ r2
~~~

Tương đương thường dựa theo `equals`; với `UNORDERED` collector, phép tương đương có thể **bỏ qua thứ tự** nếu thứ tự không thuộc hợp đồng kết quả.

### Custom Collector hợp lệ

~~~java
Collector<String, ?, List<String>> listCollector =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        });

List<String> list = values.parallelStream().collect(listCollector);
~~~

Đây là ví dụ sử dụng `java.util.stream.*` và `java.util.*`. `supplier` tạo list mới; `accumulator` thêm từng phần tử; `combiner` nối từ trái sang phải. Hàm combiner trả `left` sau khi merge; đoạn code không cố dùng `right` sau khi kết quả đã bị chuyển vào `left`.

**Không khai báo collector này là `CONCURRENT`**, vì `ArrayList` không an toàn khi nhiều thread đồng thời gọi accumulator trên **cùng container**. Việc một collector dùng được cho parallel stream **không có nghĩa nó là concurrent collector**.

### Sai lầm về combiner

~~~java
// SAI: làm mất phần bên phải trong quá trình merge.
(left, right) -> left

// SAI nếu kết quả cần thứ tự left -> right:
// kết quả bị đổi thứ tự các phân đoạn.
(left, right) -> {
    right.addAll(left);
    return right;
}
~~~

Với một phép gộp để tạo List có thứ tự, combiner phải ghép các phần kết quả theo đúng encounter order. Nếu nhận hai phần `[a,b]` và `[c,d]`, kết quả hợp lệ là `[a,b,c,d]`; đảo thành `[c,d,a,b]` là sai với một collector muốn bảo toàn thứ tự.

### Fresh supplier quan trọng như thế nào?

~~~java
// SAI: mỗi lần supplier lại đưa đúng một list dùng chung.
List<String> shared = new ArrayList<>();
Supplier<List<String>> wrongSupplier = () -> shared;
~~~

Đối với collector không concurrent, mỗi container được cung cấp cần riêng và đủ độc lập để implementation quản lý các phân đoạn. Một supplier đưa cùng shared state khiến sự cô lập biến mất. Dùng `ArrayList::new` hoặc `() -> new ArrayList<>()`.

## 9. `Collector.Characteristics` không thay các luật toán học

| Đặc tính | Ý nghĩa đúng | Không có nghĩa |
| --- | --- | --- |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng result container | Mọi collector chạy parallel tự động đồng thời cập nhật cùng container |
| `UNORDERED` | Kết quả không cam kết giữ encounter order | Có thể tùy tiện làm sai tập phần tử/tổng |
| `IDENTITY_FINISH` | Finisher là phép identity và có thể được bỏ qua | Có thể mutate/share input tùy ý |

Theo hướng dẫn Stream, một phép **concurrent reduction** có thể dùng khi:

1. Stream chạy song song.
2. Collector có `CONCURRENT`.
3. **Stream unordered hoặc collector có `UNORDERED`**.

Vì vậy `CONCURRENT` một mình không có nghĩa sẽ concurrent reduction cho mọi ordered stream. Với ordered stream và collector concurrent nhưng **không unordered**, implementation vẫn có thể dùng chiến lược partition rồi combine để bảo toàn ràng buộc order.

Không gắn `IDENTITY_FINISH` khi finisher thực sự đổi accumulator từ kiểu `A` sang kiểu `R` (ví dụ gói thành một object summary khác), vì một cast/bỏ qua finisher có thể sai kiểu. Không gắn `UNORDERED` cho collector cần List theo thứ tự gặp phần tử.

## 10. Thứ tự encounter khác thứ tự chạy callback

Đối với Stream, có ít nhất ba ý niệm khác nhau:

- **Encounter order:** thứ tự logic mà nguồn và các operation quy định. `List`/array có thứ tự gặp phần tử; `HashSet` không hứa encounter order. `sorted` áp thứ tự, `unordered()` gỡ ràng buộc thứ tự.
- **Execution order:** thứ tự thật trong đó `map`/`filter`/`forEach` và các nhánh accumulator được **gọi** theo thời gian. Parallel pipeline có thể xen kẽ trên nhiều thread.
- **Result order:** thứ tự được cam kết của **kết quả terminal operation**. Một collector ordered có thể dựng lại kết quả đúng encounter order ngay cả khi các bước xử lý từng phần tử chạy ngoài thứ tự.

Ví dụ:

~~~java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> orderedResult = source.parallelStream()
    .map(x -> x * 2)
    .collect(Collectors.toList());
// [2, 4, 6, 8, 10, 12].
~~~

**Không suy từ list kết quả đúng thứ tự rằng các lần gọi `map` thực hiện đúng 1 rồi 2 rồi 3 ...**. Implementation có thể tính `map(5)` trước `map(2)` nhưng cuối cùng vẫn tạo List theo encounter order.

### `forEach` và `forEachOrdered`

~~~java
source.parallelStream().forEach(System.out::println);
~~~

`forEach` **không cam kết thứ tự cập nhật**; nội dung in ra có thể thay đổi qua mỗi lần chạy, và callback có thể chạy trên nhiều thread. Không viết expected stdout tuyến tính 1→6 cho pipeline trên.

~~~java
source.parallelStream().forEachOrdered(System.out::println);
~~~

`forEachOrdered` áp thứ tự **encounter order** khi stream có thứ tự; với nguồn List ở trên, stdout của các giá trị sẽ theo 1→6. Tuy nhiên, nó **không hứa dùng cùng một thread**, và việc ép thứ tự side effect có thể giảm lợi ích song song.

Ngay cả khi mục tiêu là một List có thứ tự, cách tốt hơn thường là:

~~~java
List<Integer> values = source.parallelStream()
    .collect(Collectors.toList());
~~~

thay vì `forEachOrdered(result::add)` vào một biến bên ngoài. `collect` nêu rõ quyền sở hữu container và luật gộp; các side effect ngoài pipeline làm thiết kế khó kiểm thử hơn.

## 11. `peek` và `map` có side effect: đừng tin số lần cập nhật

Javadoc Stream khuyến nghị các behavioral parameters **stateless, non-interfering**. Trong một số pipeline, implementation có thể bỏ qua toàn bộ operation trung gian nếu không ảnh hưởng kết quả terminal. Vì vậy:

~~~java
AtomicInteger observed = new AtomicInteger();

long count = Stream.of("a", "b", "c")
        .peek(x -> observed.incrementAndGet())
        .count();
~~~

Không được dùng `observed.get()` làm số lượng phần tử nghiệp vụ đã xử lý. Với một nguồn đã biết kích thước và terminal `count()`, JVM có thể tính count trực tiếp mà không chạy từng `peek`. `AtomicInteger` làm phép tăng thread-safe, **không biến callback side effect thành điều bắt buộc**.

Dùng:

~~~java
long count = Stream.of("a", "b", "c").count();
// 3.
~~~

Nếu cần log debug, `peek` có thể hữu ích nhưng phải hiểu rằng hành vi quan sát phụ thuộc cách pipeline được tối ưu và các stage khác. Với các operation terminal `forEach` và `forEachOrdered`, hành động là mục đích trực tiếp của operation, nhưng vẫn cần xử lý thứ tự/concurrency theo hợp đồng.

Dùng `LongAdder` hoặc `AtomicInteger` cho **bộ đếm độc lập** trong hệ thống có nhu cầu thực, không lạm dụng chúng để thay thế result reduction.

## 12. Biến tích lũy dùng chung: thread safety không đồng nghĩa correctness

Một biến cục bộ trong vòng lặp tuần tự là nơi tích lũy hợp lệ:

~~~java
int total = 0;
for (int value : numbers) {
    total += value;
}
~~~

Nhưng khi chuyển sang parallel stream:

~~~java
// SAI: không được dùng shared int làm accumulator của parallel forEach.
int[] total = {0};
numbers.parallelStream().forEach(x -> total[0] += x);
~~~

`total[0] += x` là một thao tác read-modify-write, **không atomic**: nhiều thread có thể cùng đọc một giá trị cũ, ghi đè kết quả của nhau và gây lost update. Kể cả chạy test nhỏ một lần ra đáp án đúng, code vẫn có data race. Một array một phần tử chỉ vượt hạn chế lambda capture final/effectively-final, **không tạo an toàn thread**.

### 12.1. `volatile` không làm phép tăng trở thành atomic

~~~java
// Ví dụ phản ánh lỗi tư duy trong class có field:
volatile int count;

// count++ không phải một thao tác atomic.
~~~

`volatile` có thuộc tính visibility/happens-before theo Java Memory Model, nhưng `++` gồm đọc, cộng và ghi nhiều bước. Để biến đếm được cập nhật atomically, có thể dùng `AtomicInteger.incrementAndGet()`, `AtomicLong.addAndGet(...)` hoặc `LongAdder.add(...)` theo yêu cầu thực tế.

### 12.2. Khi nào `AtomicLong`/`LongAdder` có ích?

- **`AtomicLong`:** các phép thêm/lấy giá trị atomic, phù hợp đếm bên ngoài stream khi thật sự cần trạng thái chia sẻ; có thể dùng `getAndAdd`/`addAndGet`. Tuy nhiên, nếu mục tiêu là tính tổng của một stream cố định, `mapToLong(...).sum()` hoặc `reduce` vẫn dễ hiểu hơn.
- **`LongAdder`:** tối ưu giảm contention cho các bộ đếm hot, nhiều thread cập nhật. `sum()` không phải một **atomic snapshot** khi có cập nhật đồng thời, nên không dùng cho bài toán cần nhìn tức thời một tổng đã commit nhất quán dưới tải.
- **`ConcurrentHashMap`:** cập nhật theo khóa với `compute`/`merge` có thể an toàn nếu dùng đúng hợp đồng; không đồng nghĩa các giá trị đọc ra có thứ tự và không biến một phép toán không kết hợp thành hợp lệ.

Đừng sử dụng một counter thread-safe chỉ để làm cho những mutation từ `map`/`peek` “đủ an toàn”; tính đúng đắn còn phụ thuộc việc callback **có chạy hay không**, **chạy bao nhiêu lần**, và liệu thứ tự có ảnh hưởng đến kết quả.

### 12.3. Tích lũy vào `synchronizedList` không bảo toàn order

~~~java
List<Integer> output = Collections.synchronizedList(new ArrayList<>());

numbers.parallelStream().forEach(output::add);
~~~

Các lần thêm vào list được đồng bộ, tránh race trên cấu trúc nội bộ, nhưng **thứ tự phần tử được thêm vẫn không cam kết là encounter order**. Lúc này output có thể là một hoán vị của input dù không bị mất phần tử.

Để nhận một List theo thứ tự nguồn, nên dùng:

~~~java
List<Integer> output = numbers.parallelStream()
        .collect(Collectors.toList());
~~~

Nếu không quan tâm thứ tự, dùng collector/tập hợp có semantics phù hợp và so bằng cách không phụ thuộc thứ tự; đừng dựa vào một lần chạy để “chứng minh” thứ tự.

## 13. `groupingByConcurrent`, `CONCURRENT` và thứ tự quan sát

Java có các collector chuẩn cho grouped reduction:

~~~java
List<String> colors =
    Arrays.asList("red", "blue", "red", "green", "blue", "red");

ConcurrentMap<String, Long> counts = colors.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Function.identity(), Collectors.counting()));
~~~

Với dữ liệu này, ý nghĩa bảng tần suất là:

~~~text
blue  -> 2
green -> 1
red   -> 3
~~~

**Không in trực tiếp `counts.toString()` rồi đòi đúng thứ tự key cố định**: `ConcurrentHashMap` không cam kết thứ tự duyệt giống sorted map. Nếu muốn output ổn định để test hoặc UI:

~~~java
System.out.println(new TreeMap<>(counts));
// {blue=2, green=1, red=3}
~~~

`groupingByConcurrent` là collector concurrent, unordered; kết quả kiểu `ConcurrentMap`. Nhưng **không tự suy mọi List được gom theo từng khóa đều có thứ tự giống nguồn**. Nếu value order quan trọng, cân nhắc `groupingBy` với ordered source, hoặc thu gom và sắp xếp theo một trường rõ nghĩa.

Một số điểm cần nhớ:

1. Concurrent collector có thể cho phép nhiều thread cập nhật **cùng result container**, không cần mỗi nhánh có map riêng.
2. Một collector concurrent không hứa mọi cấu trúc phụ chứa trong map đều có thể được client đồng thời sửa **sau khi collect kết thúc**; xét hợp đồng cụ thể của kết quả.
3. `groupingByConcurrent(..., counting())` thích hợp khi chỉ cần tần suất theo khóa không cần thứ tự kết quả.
4. `groupingBy(...)` trả `Map` và merge các map riêng có thể tốn chi phí trong parallel; không mặc định `groupingByConcurrent` luôn nhanh hơn, cần đo trên dữ liệu thực.
5. Kết quả có thể **tương đương theo key và count** dù thứ tự cập nhật từng key không xác định.

### Mỗi lần update xảy ra ở đâu?

Với collector không concurrent, stream framework có thể giữ container ở từng partition rồi gộp. Với concurrent collector được phép chạy concurrent reduction, framework có thể cùng đưa phần tử vào một map chung. Đây là **hai cơ chế khác nhau**; người viết collector phải công bố đúng characteristic để framework dùng đúng, không gắn nhãn `CONCURRENT` nhằm “ép performance” khi container thực tế không thread-safe.

## 14. Bảo toàn kết quả theo order: kết hợp được không có nghĩa muốn đảo tùy ý

Một List được tạo bằng concat có thể **kết hợp**:

~~~text
([a] + [b]) + [c] = [a] + ([b] + [c]) = [a,b,c]
~~~

Nhưng concat không giao hoán:

~~~text
[a] + [b] = [a,b]
[b] + [a] = [b,a]
~~~

Vì thế với List có encounter order, **combiner phải giữ quan hệ trái–phải**. Trong collector:

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

cách gộp theo thứ tự phân đoạn khác với đảo `right.addAll(left)`. Nếu dùng `unordered()` để tối ưu, chỉ làm khi **nghiệp vụ thực sự không cần thứ tự**. `unordered()` không phải một cách sửa một collector vốn đang có race condition.

### Cần một phần tử “cuối cùng” nghĩa là gì?

Nếu `latest` nghĩa là phần tử có timestamp lớn nhất, **đừng dùng “phần tử nào được cập nhật cuối trong parallel forEach”** để suy latest. Thread nào xong cuối là lịch thực thi, không phản ánh timestamp hay encounter order.

~~~java
Optional<Event> latest = events.stream()
        .max(Comparator.comparing(Event::getOccurredAt));
~~~

Đây là snippet minh họa cho class `Event` do ứng dụng định nghĩa, method `getOccurredAt()` trả kiểu thời gian có thứ tự (ví dụ `Instant`). Nếu có timestamp trùng nhau, thêm tie-breaker theo ID/sequence nếu muốn kết quả duy nhất, ổn định.

Nếu cần phần tử **cuối encounter order** của một ordered stream, phải giữ encounter order và chọn thuật toán có hợp đồng rõ. Không áp `unordered()` rồi mong terminal operation tự khôi phục thứ tự đã bỏ.

## 15. Thiết kế accumulator tùy biến: kiểm tra từng luật

Trước khi đưa một collector tự viết lên dữ liệu thật, hãy xác minh các tính chất bằng một bộ kiểm thử nhỏ:

**Identity với container trống**

~~~text
accumulate([a,b]) = [a,b]
combine([a,b], emptyList) = [a,b]
=> hợp lệ.
~~~

**Associativity / split equivalence**

~~~text
Một lượt: add(a), add(b), add(c) => [a,b,c]

Chia nhánh:
  left: add(a), add(b) => [a,b]
  right: add(c)       => [c]
  combine(left,right) => [a,b,c]

=> equivalent với một lượt.
~~~

**Không chia sẻ supplier**

~~~java
// ĐÚNG:
Supplier<List<String>> supplier = ArrayList::new;

// SAI: cả các lời gọi trả một object chung.
List<String> shared = new ArrayList<>();
Supplier<List<String>> wrong = () -> shared;
~~~

**Đúng characteristic**

~~~text
ArrayList mutable accumulator:
    sử dụng bình thường trong collect song song
    nhưng KHÔNG có đặc tính CONCURRENT.

ConcurrentHashMap accumulator được thiết kế an toàn:
    có thể cân nhắc CONCURRENT nếu toàn bộ hợp đồng cũng đúng.
    nếu kết quả không cần encounter order, cân nhắc UNORDERED.
~~~

**Finisher**

Nếu finisher chỉ trả cùng accumulator khi kết thúc, có thể dùng `IDENTITY_FINISH`. Nếu finisher chuyển một mutable container thành summary immutable, hãy để finisher chạy và **không** khai báo `IDENTITY_FINISH`.

### Một phép thử thủ công cho combiner

~~~java
List<String> left = new ArrayList<>(Arrays.asList("a", "b"));
List<String> right = new ArrayList<>(Collections.singletonList("c"));

left.addAll(right);
System.out.println(left);
// [a, b, c].
~~~

Đây là phép thử đơn giản, nhưng không đủ để chứng minh mọi case. Test thêm nguồn rỗng, nguồn một phần tử, cùng dữ liệu chia theo nhiều partition, dữ liệu có phần tử trùng, và các trường hợp đặc biệt của domain.

## 16. Độ đúng của số nguyên khi overflow

`Integer::sum` có tính kết hợp theo **số nguyên `int` 32-bit với phép cộng wrap**. Nhưng nếu hệ thống đang tính tổng tiền theo nghĩa toán học, overflow khiến số bị sai dù kết quả vẫn có thể nhất quán theo luật bit-level. Ví dụ `Integer.MAX_VALUE + 1` không thể biểu diễn bằng `int` dương.

Giải pháp:

- Nếu biết miền tổng an toàn trong `long`, dùng `mapToLong(...).sum()` hoặc `reduce(0L, Long::sum)`.
- Nếu không chấp nhận overflow, có thể dùng `Math.addExact` với kiểm tra và xử lý `ArithmeticException`, hoặc dùng `BigInteger` khi miền quá lớn.
- Với tiền, chọn biểu diễn số thập phân/đơn vị tiền chính xác (`BigDecimal` hoặc số nguyên đơn vị nhỏ) theo chính sách scale/rounding; không dùng `double` nếu cần cân đối tuyệt đối.
- Dù chọn kiểu nào, xác minh identity và combiner tương thích. Một kiểu số lớn hơn **không khắc phục** một accumulator có side effect hoặc một combiner không kết hợp.

## 17. Performance và khả năng quan sát

Một parallel stream có thể nhanh hơn, chậm hơn hoặc tương đương sequential tùy khối lượng dữ liệu, chi phí phép tính, overhead chia/gộp, khả năng phân đoạn của `Spliterator`, số core và contention. Không có bảo đảm rằng `parallel()` tự động tăng tốc.

Các nguyên tắc tốt:

- Đo bằng benchmark có warmup và dữ liệu đại diện; nếu benchmark Java nghiêm túc, sử dụng công cụ chuyên dụng như JMH.
- Tránh log hay truy cập IO nặng bên trong `map`, `filter`, `reduce`, `combiner` làm sai mục tiêu song song.
- Không dùng thứ tự log để khẳng định thứ tự encounter.
- Không gắn `CONCURRENT` cho collector chỉ vì muốn bớt merge; container phải thực sự hỗ trợ concurrent accumulator.
- Với `forEachOrdered`, nếu mục tiêu chỉ là tạo List kết quả, `collect` thường vừa rõ hợp đồng vừa dễ tối ưu.
- Kiểm thử với `parallelStream()` **không bảo đảm** mọi lỗi race condition sẽ lộ trong một lần chạy. Phải kiểm tra đúng luật và các giả định thread safety trước.

## 18. Chương trình Java đầy đủ: kiểm chứng các luật tích lũy

Tạo file **`AccumulatorLawsDemo.java`**. Mã độc lập, chỉ dùng các API có từ Java 8, biên dịch/chạy bằng JDK 17+ và không cần thư viện ngoài.

Điểm thiết kế của ví dụ:

- Các đầu ra được in từ `reduce`/`collect` hợp lệ và dữ liệu cố định.
- Những phép toán identity sai, trừ không kết hợp được tính theo **hai cách nhóm minh họa tường minh**, không phụ thuộc lịch chạy ngẫu nhiên của parallel stream.
- `forEach` không in thứ tự thread-scheduling; nó gom đủ phần tử vào `ConcurrentLinkedQueue` rồi **sort trước khi in**, nên stdout ổn định. `forEachOrdered` minh họa encounter order được bảo toàn khi nguồn có thứ tự.
- Map tần suất concurrent được chuyển qua `TreeMap` **chỉ để hiển thị** với thứ tự khóa ổn định.
- Có các phép `check(...)` để phản hồi `AssertionError` nếu vi phạm kỳ vọng; stdout cuối `all checks passed` chỉ xuất hiện khi mọi kiểm tra đều đạt.

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import java.util.stream.*;

public final class AccumulatorLawsDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);
        List<String> words = Arrays.asList("java", "stream", "api");

        int sequentialSum = numbers.stream().reduce(0, Integer::sum);
        int parallelSum = numbers.parallelStream().reduce(0, Integer::sum);
        int product = numbers.parallelStream().reduce(1, (a, b) -> a * b);
        boolean optionalPresent = Stream.<Integer>empty()
                .reduce(Integer::sum).isPresent();
        int emptySum = Stream.<Integer>empty().reduce(0, Integer::sum);

        System.out.println("sum sequential: " + sequentialSum);
        System.out.println("sum parallel: " + parallelSum);
        System.out.println("product parallel: " + product);
        System.out.println("empty reduce Optional present: " + optionalPresent);
        System.out.println("empty reduce with identity: " + emptySum);

        int wrongSequential = 100 + 1 + 2 + 3;
        int wrongSplit = (100 + 1) + (100 + 2 + 3);
        System.out.println("wrong identity sequential model: " + wrongSequential);
        System.out.println("wrong identity split model: " + wrongSplit);
        System.out.println("subtraction left grouping: " + ((10 - 3) - 2));
        System.out.println("subtraction right grouping: " + (10 - (3 - 2)));

        int mapped = words.parallelStream().reduce(
                0, (sum, word) -> sum + word.length(), Integer::sum);
        System.out.println("three-arg reduce length: " + mapped);
        System.out.println("mapToInt sum length: " +
                words.parallelStream().mapToInt(String::length).sum());

        String joined = Stream.of("a", "b", "c")
                .parallel().reduce("", String::concat);
        System.out.println("parallel ordered concatenation: " + joined);

        List<String> collected = words.parallelStream()
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        List<String> collectedWithStandard = words.parallelStream()
                .collect(Collectors.toList());
        System.out.println("collect three args: " + collected);
        System.out.println("collect toList: " + collectedWithStandard);

        List<String> usingCustomCollector = words.parallelStream().collect(
                Collector.of(
                    () -> new ArrayList<String>(),
                    ArrayList::add,
                    (left, right) -> { left.addAll(right); return left; }));
        System.out.println("custom collector: " + usingCustomCollector);

        ConcurrentMap<String, Long> counts = Arrays.asList(
                "red", "blue", "red", "green", "blue", "red")
                .parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(), Collectors.counting()));
        System.out.println("concurrent counts sorted keys: " +
                new TreeMap<>(counts));

        Queue<Integer> observed = new ConcurrentLinkedQueue<>();
        numbers.parallelStream().forEach(observed::add);
        List<Integer> sortedObserved = new ArrayList<>(observed);
        Collections.sort(sortedObserved);
        System.out.println("parallel forEach observed sorted: " + sortedObserved);

        List<Integer> orderedEffects =
                Collections.synchronizedList(new ArrayList<>());
        numbers.parallelStream().forEachOrdered(orderedEffects::add);
        System.out.println("parallel forEachOrdered: " + orderedEffects);

        double left = (1e16 + -1e16) + 1.0;
        double right = 1e16 + (-1e16 + 1.0);
        System.out.println("floating left group: " + left);
        System.out.println("floating right group: " + right);

        check(sequentialSum == 21 && parallelSum == 21, "addition reduction");
        check(product == 720, "multiplication reduction");
        check(!optionalPresent && emptySum == 0, "empty reduction");
        check(wrongSequential != wrongSplit, "wrong identity demonstrator");
        check(mapped == 13, "reduce accumulator compatibility");
        check(joined.equals("abc"), "ordered concat");
        check(collected.equals(words)
                && collectedWithStandard.equals(words)
                && usingCustomCollector.equals(words), "encounter order");
        check(counts.get("red") == 3L && counts.get("blue") == 2L
                && counts.get("green") == 1L, "concurrent counting");
        check(sortedObserved.equals(numbers) && observed.size() == 6,
                "parallel forEach values");
        check(orderedEffects.equals(numbers), "forEachOrdered encounter order");
        check(left != right, "floating grouping caution");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AccumulatorLawsDemo.java
java AccumulatorLawsDemo
~~~

**Kết quả stdout chính xác đã kiểm thử:**

~~~text
sum sequential: 21
sum parallel: 21
product parallel: 720
empty reduce Optional present: false
empty reduce with identity: 0
wrong identity sequential model: 106
wrong identity split model: 206
subtraction left grouping: 5
subtraction right grouping: 9
three-arg reduce length: 13
mapToInt sum length: 13
parallel ordered concatenation: abc
collect three args: [java, stream, api]
collect toList: [java, stream, api]
custom collector: [java, stream, api]
concurrent counts sorted keys: {blue=2, green=1, red=3}
parallel forEach observed sorted: [1, 2, 3, 4, 5, 6]
parallel forEachOrdered: [1, 2, 3, 4, 5, 6]
floating left group: 1.0
floating right group: 0.0
all checks passed
~~~

### Phân tích những kết quả quan trọng

1. **Hai tổng bằng 21:** `0` là identity của phép cộng; phép cộng `int` cho miền 1–6 không tràn, nên reduction hợp lệ cho cả tuần tự và song song.
2. **Tích bằng 720:** `1` là identity của phép nhân; phép nhân nguyên trong miền này không tràn.
3. **Stream rỗng:** overload không identity trả `Optional.empty`; overload có identity 0 trả 0, nhưng chúng có ý nghĩa nghiệp vụ khác nhau.
4. **Identity sai 100:** cùng ba phần tử, tính một lượt được 106 còn mô hình chia hai phần được 206. Không khẳng định JVM phải chia nhánh giống mô hình.
5. **Phép trừ:** hai cách đặt ngoặc trả 5 và 9, chứng minh không kết hợp.
6. **Ba đối số `reduce`:** tổng độ dài `4 + 6 + 3 = 13`; `mapToInt(...).sum()` cho cùng kết quả, thường đọc dễ hơn.
7. **Nối chuỗi:** `"abc"` giữ encounter order của nguồn ordered, dù phép toán nối chuỗi không giao hoán.
8. **Ba cách `collect`:** container tươi và combiner nối đúng chiều tạo `[java, stream, api]`.
9. **Map concurrent:** tần suất đúng, `TreeMap` tạo thứ tự key khi in. Không suy thứ tự update từ thứ tự key đã sort.
10. **`forEach`:** kết quả được **sort trước khi in**, không khẳng định action ban đầu đã chạy theo thứ tự tăng dần.
11. **`forEachOrdered`:** bảo toàn encounter order cho nguồn List này; không hứa cùng thread.
12. **Số thực:** hai cách nhóm cho 1.0 và 0.0 vì rounding, dù phép cộng toán học có tính kết hợp. Không dùng so bitwise equality của tổng `double` làm điều kiện duy nhất cho mọi parallel reduction.
13. **`all checks passed`:** chương trình chỉ in sau khi 11 phép kiểm tra về kết quả, identity, tần suất, thứ tự kết quả và hiệu ứng floating point đều thành công.

Các case lỗi identity/mutable accumulator trong phần giải thích được trình bày như **phản ví dụ**, không chạy như một pipeline production; điều đó tránh tạo expected stdout cố định cho hành vi vốn không được đặc tả.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao sai hoặc không ổn định | Cách làm đúng |
| --- | --- | --- |
| Dùng `100` làm identity để cộng | Identity bị cộng cho mỗi phân đoạn; không là phần tử đơn vị | Dùng `0` |
| Dùng `0` làm identity để nhân | Mọi tích bị về 0 | Dùng `1` |
| Dùng phép trừ trong parallel reduce | Phép trừ không kết hợp | Đổi bài toán thành phép kết hợp hợp lệ hoặc xử lý tuần tự |
| Giả định assoc và commutative là một | Nối chuỗi assoc nhưng không commutative | Giữ encounter order với collector/reduce phù hợp |
| Dùng mutable `ArrayList` làm identity của `reduce` | State dùng chung, có thể bị mutate nhiều nhánh | Dùng `collect` và supplier tạo container mới |
| Supplier trả cùng một object global | Không còn isolation giữa các nhánh | `ArrayList::new` hoặc factory tạo mới |
| Combiner chỉ trả `left` mà không gộp `right` | Mất dữ liệu ở các partition khác | Gộp đủ mọi phần tử |
| Combiner đảo `right.addAll(left)` cho List ordered | Mất encounter order của kết quả | Giữ thứ tự left rồi right |
| Khai báo `CONCURRENT` cho collector dùng `ArrayList` | Cùng container có thể bị sửa nhiều thread | Để collector non-concurrent hoặc dùng cấu trúc an toàn thật |
| Dùng `UNORDERED` khi thứ tự có ý nghĩa | Kết quả có thể bị đảo dù đủ phần tử | Giữ ordered semantics |
| Đoán `CONCURRENT` tự động luôn chạy đồng thời | Còn phụ thuộc unordered source/collector và implementation | Hiểu các điều kiện concurrent reduction |
| In `ConcurrentHashMap` rồi so chuỗi theo key order | Map không có thứ tự duyệt đảm bảo | Chuyển `TreeMap` khi cần sorted output |
| Dùng `parallelStream().forEach(list::add)` trên `ArrayList` | Race, lost-update, corrupt list | `collect(Collectors.toList())` |
| Thay `ArrayList` bằng `synchronizedList` rồi nghĩ có order | Thread-safe add không cố định thứ tự thread gọi | Dùng ordered collector/`forEachOrdered` khi thực sự cần |
| Nghĩ `forEachOrdered` buộc mọi callback trên một thread | Chỉ cam kết encounter order/happens-before, không thread identity | Không phụ thuộc thread |
| Dùng `volatile int` rồi `count++` | `volatile` không biến read-modify-write thành atomic | `AtomicInteger`/`LongAdder` nếu cần shared counter |
| Dùng `AtomicInteger` trong `peek` rồi lấy count làm kết quả | Side effect có thể bị tối ưu bỏ trong một số pipeline | Terminal `count()` để đếm |
| Quan sát thứ tự log rồi suy thứ tự kết quả | Parallel scheduling không đồng nghĩa encounter order | Dùng dữ liệu kết quả và contract terminal |
| Dùng `Integer::sum` khi tổng vượt int | Kết quả toán học overflow | `long`/`BigInteger`/checked arithmetic |
| Giả định phép cộng `double` kết hợp tuyệt đối | Floating rounding phụ thuộc grouping | Xác định accuracy/tolerance hoặc số thập phân chính xác |
| `reduce` trên stream rỗng trả 0 trong mọi overload | Overload không identity trả Optional.empty | Chọn overload theo domain |
| Stream đã terminal rồi dùng lại | Stream chỉ duyệt một lần | Tạo stream mới từ source |
| Coi kết quả đúng một lần là chứng minh parallel-safe | Race và thứ tự có thể thay đổi theo scheduler | Kiểm luật, kiểm thread safety và chạy test theo cấu hình |
| Cứ thêm `parallel()` để nhanh | Overhead split/combine có thể lớn hơn lợi ích | Benchmark dữ liệu thực |
| Dùng collector sai finisher characteristic | Có thể trả sai kiểu hoặc bỏ chuyển đổi cần thiết | Khai báo `IDENTITY_FINISH` chỉ khi đúng hợp đồng |

## 20. Bài tập tự luyện có đáp án

### Bài 1 — Chọn identity cho phép cộng

Một stream chứa `[4, 5, 6]`, bạn muốn tổng bằng 15 cả khi tuần tự lẫn song song. Identity và accumulator là gì?

**Đáp án:** `0` và `Integer::sum`. Vì `0 + x = x`, và cộng trong miền này kết hợp; có thể dùng `stream.reduce(0,Integer::sum)`.

### Bài 2 — Vì sao `100` không hợp lệ?

Dùng `reduce(100,Integer::sum)` trên `[1,2,3]`. Mô hình tuần tự và mô hình hai partition trả gì?

**Đáp án:** Một lượt đơn giản là 106; nếu nhóm `[1]` và `[2,3]` mỗi nhóm khởi tạo 100 rồi gộp bằng cộng, kết quả 206. Các cách chia khác có thể cho số khác nữa. 100 không phải identity nên giảm song song không có kết quả tương đương được bảo đảm.

### Bài 3 — Kiểm tính kết hợp

Là phép toán `a - b` kết hợp không? Kiểm tra với 10, 3, 2.

**Đáp án:** Không: `(10-3)-2=5` và `10-(3-2)=9`. Tránh dùng nó làm accumulator của parallel reduce với ý định “trừ theo thứ tự”.

### Bài 4 — Nối chuỗi song song

Nối `"a"`, `"b"`, `"c"` có kết hợp không, có giao hoán không? Nếu nguồn ordered, có thể dùng `reduce("",String::concat)` không?

**Đáp án:** Có tính kết hợp, không giao hoán. Với source ordered và reduction tuân hợp đồng, kết quả là `"abc"`, không cần yêu cầu các phép concat phải thực thi trên một thread hay theo thứ tự thời gian.

### Bài 5 — Kết quả kiểu khác phần tử

Có `Stream<String>` gồm `"java"` và `"api"`. Viết `reduce` ba đối số ra tổng độ dài.

**Đáp án:**

~~~java
int length = Stream.of("java", "api")
    .reduce(0, (sum, s) -> sum + s.length(), Integer::sum);
// 7.
~~~

Ở đây identity `0`, combiner cộng và accumulator cộng độ dài; các luật tương thích được thỏa. Có thể viết gọn `mapToInt(String::length).sum()`.

### Bài 6 — Mutable list trong reduce

Vì sao không nên viết `reduce(new ArrayList<>(), (list,x)->{list.add(x);return list;}, ...)` để tích lũy danh sách?

**Đáp án:** Biến identity mutable có thể được dùng chung giữa các phân đoạn; callback mutate state, vi phạm semantics value reduction và có thể tạo duplicate/race. Dùng `collect(ArrayList::new,ArrayList::add,ArrayList::addAll)` hoặc `Collectors.toList()`.

### Bài 7 — Combiner trong Collector

Hai container là `[a,b]` và `[c,d]`. Nếu target là List ordered, combiner đúng nên trả gì?

**Đáp án:** `[a,b,c,d]` theo thứ tự left–right. Trả `left` mà không thêm right làm mất dữ liệu; đảo right–left làm hỏng encounter order.

### Bài 8 — `forEach` và `forEachOrdered`

Với source List `[1,2,3,4]`, xử lý `parallelStream().forEach(print)` có bắt buộc in 1→4 không? `forEachOrdered` thì sao?

**Đáp án:** `forEach` không cam kết thứ tự; `forEachOrdered` duy trì encounter order của ordered stream. `forEachOrdered` không hứa callback được thực thi cùng thread.

### Bài 9 — `volatile` có sửa race không?

Một field `volatile int sum` được nhiều thread chạy `sum += value`. Có an toàn atomic không?

**Đáp án:** Không. `volatile` không bảo đảm atomic read-modify-write. Nhưng ngay cả khi thay bằng `AtomicInteger`, cách tích lũy kết quả stream được khuyến nghị vẫn là `reduce` hoặc `collect`; atomic counter không bảo đảm thứ tự hay số lần callback trung gian.

### Bài 10 — Collector concurrent

Một collector có `CONCURRENT` nhưng không `UNORDERED`, stream song song có encounter order và chưa gọi `unordered()`. Có thể khẳng định nó luôn cập nhật cùng một container từ nhiều thread không?

**Đáp án:** Không. Theo điều kiện concurrent reduction, stream phải unordered hoặc collector phải `UNORDERED` bên cạnh `CONCURRENT`. Implementation còn được phép chọn chiến lược reduction phù hợp; không hứa thread scheduling cụ thể.

### Bài 11 — Ghi log từ `peek`

`stream.peek(x -> counter.incrementAndGet()).count()` có bảo đảm counter bằng count không?

**Đáp án:** Không. Với một số nguồn/pipeline, terminal `count()` có thể lấy kích thước mà không gọi hết các stage trung gian. `counter` không phải kết quả đáng tin. Đếm bằng `count()` và chỉ dùng `peek` cho tác vụ debug khi hiểu giới hạn.

### Bài 12 — Double sum khác nhau

Vì sao `(1e16 + -1e16) + 1.0` và `1e16 + (-1e16 + 1.0)` khác?

**Đáp án:** Làm tròn floating point có thể làm mất số 1 khi cộng với giá trị rất lớn. Khi phép cộng được nhóm khác, kết quả có thể khác; quy định tolerance hoặc dùng số thập phân chính xác cho domain cần exact.

### Bài 13 — Tần suất và thứ tự key

Một `groupingByConcurrent(..., counting())` trả Map tần suất đúng nhưng khi in ra thứ tự key có thể khác. Có phải sai luật collector?

**Đáp án:** Không nếu domain không yêu cầu key order. Để hiển thị ổn định, dùng `new TreeMap<>(map)`. Nếu cần giữ thứ tự phần tử **bên trong mỗi nhóm**, không dựa vào một collector concurrent unordered.

### Bài 14 — Lấy record mới nhất

Nhóm parallel `forEach` và biến `lastSeen` được cập nhật sau cùng có chắc là phần tử timestamp lớn nhất không?

**Đáp án:** Không. Lịch chạy thread không phản ánh thời điểm event hoặc encounter order. Dùng `max(Comparator.comparing(...))` và một tie-breaker domain xác định khi timestamp trùng.

## 21. Checklist cho review và kiểm thử

- [ ] Identity là phần tử đơn vị thật sự cho phép gộp? Đã test cả trái và phải?
- [ ] Với `reduce` ba đối số, combiner identity, associativity và compatibility với accumulator đều được kiểm tra?
- [ ] Operation có associativity theo **semantics thực của kiểu** (`double` có rounding, `int` có overflow)?
- [ ] Không nhầm tính kết hợp với giao hoán?
- [ ] Không dùng mutable shared identity với `reduce`?
- [ ] Với `collect`, mỗi lần supplier có tạo container độc lập?
- [ ] Accumulator có đưa phần tử vào đúng container được cung cấp?
- [ ] Combiner có gộp đủ dữ liệu, theo đúng chiều encounter order khi cần?
- [ ] Collector có tuân identity/split-equivalence khi test theo nhiều partitions?
- [ ] Đặc tính `CONCURRENT`/`UNORDERED`/`IDENTITY_FINISH` có đúng implementation?
- [ ] Side effect callback có thật sự stateless/non-interfering?
- [ ] Không dùng shared `ArrayList`, shared primitive array hay `volatile++` để tích lũy song song?
- [ ] Khi dùng `AtomicLong`/`LongAdder`, có phân biệt thread safety và yêu cầu snapshot?
- [ ] Thứ tự encounter, thứ tự chạy callback và thứ tự kết quả đã được phân biệt?
- [ ] Có chọn `forEachOrdered` chỉ khi side effect thật sự cần thứ tự?
- [ ] Không dùng `peek` counter làm dữ liệu nghiệp vụ?
- [ ] Với Map/Set unordered, test theo key/value/set equality thay vì `toString` order?
- [ ] Với ordered List, test bằng encounter order, không bằng log thread?
- [ ] Đã test rỗng, một phần tử, phần tử lặp, input lớn, số âm, overflow, floating rounding?
- [ ] Khi domain cần bản ghi “mới nhất”, có comparator rõ theo timestamp/sequence?
- [ ] Đã đo performance thay vì giả định parallel stream luôn nhanh hơn?
- [ ] Không tái sử dụng stream sau terminal operation?
- [ ] Mã ví dụ và stdout được biên dịch/chạy kiểm thử thực tế?

**Kết luận:** Một phép tích lũy đúng trong Java Stream không chỉ là “cộng biến trong vòng lặp”. `Identity` phải trung hòa phép gộp; `associativity` cho phép nhóm lại từng partition mà vẫn tương đương; `accumulator/combiner` phải tương thích; mutable reduction cần các container do `supplier` cung cấp và đặc tính concurrent đúng sự thật. Cuối cùng, **thứ tự callback được thực thi không phải encounter order**, dù kết quả thu thập theo ordered stream vẫn có thể đúng thứ tự. Hãy thiết kế theo hợp đồng kết quả, không theo lịch chạy ngẫu nhiên của thread.

### Tài liệu chính thức (Java SE 26, API còn được hỗ trợ)

- [`java.util.stream` package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html): reduction, identity, associativity, parallel ordering, side effects, stateless/non-interfering và concurrent reduction.
- [`Stream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): ba dạng `reduce`, `collect`, `forEach`/`forEachOrdered`, `peek` và `unordered`.
- [`Collector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): identity constraint, associativity constraint, supplier/accumulator/combiner/finisher và thread confinement.
- [`Collector.Characteristics`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html): `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`.
- [`Collectors`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `toCollection`, `groupingBy` và `groupingByConcurrent`.
- [`LongAdder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): cập nhật counter dưới contention và giới hạn atomic snapshot của `sum()`.
