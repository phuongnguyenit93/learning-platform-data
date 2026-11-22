# Kiểm tra tính kết hợp và phần tử đơn vị của phép rút gọn trong Java Stream

## 1. Mục tiêu bài học

Khi viết **Stream.reduce(...)**, việc chương trình cho đúng kết quả với một ví dụ nhỏ **chưa đủ** để kết luận phép rút gọn đúng. Stream có thể chia nguồn thành nhiều phần và gộp kết quả từng phần, nhất là khi chạy **parallel**. Vì vậy, phép rút gọn cần tuân thủ các **luật đại số** nhất định để kết quả không phụ thuộc vào cách chia và kết hợp công việc.

Hai luật nền tảng là:

- **Phần tử đơn vị (identity):** kết hợp một giá trị với identity không làm thay đổi giá trị đó.
- **Tính kết hợp (associativity):** thay cách đặt ngoặc trong chuỗi kết hợp không làm thay đổi kết quả theo quan hệ tương đương đã xác định.

Với overload `reduce(identity, accumulator, combiner)`, còn cần kiểm tra **tính tương thích (compatibility)** giữa cách tích lũy phần tử và cách kết hợp kết quả từng phần.

Sau bài, bạn có thể:

1. Phân biệt ba overload của `reduce()`, nhận diện identity và phép kết hợp tương ứng.
2. Viết test identity hai chiều, associativity và compatibility đúng ngữ nghĩa Java.
3. Phát hiện phép trừ, “giá trị ban đầu” không phải identity, combiner sai và accumulator mutable chia sẻ.
4. Kiểm thử cả nguồn rỗng, một phần tử, số âm, giá trị biên, phân hoạch và chạy tuần tự/song song.
5. Hiểu sự khác nhau giữa tính đúng **theo semantics số nguyên Java** và tính đúng **theo yêu cầu nghiệp vụ**.
6. Đánh giá phép cộng `double`, `BigDecimal`, nối chuỗi và các phép kết hợp không giao hoán.
7. Dùng test trên bộ mẫu có chủ đích và test ngẫu nhiên có seed xác định để phát hiện lỗi, nhưng không đánh đồng test với chứng minh toán học.

## 2. Tại sao reduce cần các luật?

Ví dụ:

~~~java
int sum = List.of(1, 2, 3, 4).parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 10
~~~

Trong một cách chạy, nguồn có thể được xử lý như:

~~~text
Nhánh trái:  1 + 2 = 3
Nhánh phải: 3 + 4 = 7
Kết hợp:    3 + 7 = 10
~~~

Hoặc theo cách khác:

~~~text
Nhánh A: 1
Nhánh B: 2
Nhánh C: 3 + 4 = 7
Kết hợp: 1 + (2 + 7) = 10
~~~

Đây là sơ đồ minh họa, **không phải cam kết JVM thực tế tạo đúng ba nhánh trên**. Ý nghĩa là framework có thể thay đổi cách nhóm phần tử nhưng vẫn phải tạo kết quả đúng với hợp đồng phép rút gọn.

Nếu thay `Integer::sum` bằng phép trừ, kết quả có thể thay đổi khi đặt ngoặc khác nhau. Nếu thay identity `0` bằng `10`, mỗi nhánh có thể mang theo giá trị 10 như một phần tử ban đầu, làm kết quả không còn là “10 cộng tổng nguồn” theo ý muốn.

**Kết luận:** cần kiểm thử **luật của phép kết hợp** chứ không chỉ thử một terminal trên một bộ dữ liệu.

## 3. Ba overload reduce() cần phân biệt

### 3.1. reduce(BinaryOperator<T>): không có identity tường minh

~~~java
Optional<Integer> maximum = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(maximum.orElse(-1)); // 9
~~~

Chữ ký:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Vì không truyền identity nên khi nguồn rỗng, kết quả là `Optional.empty()`. Phép kết hợp vẫn cần **associative**. Đây là lựa chọn hữu ích khi không có một giá trị identity hợp lệ cho toàn miền.

~~~java
Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::max);

System.out.println(none.isEmpty()); // true
~~~

Các mảnh ghép này cần import `Optional`, `List`, `Stream`.

### 3.2. reduce(identity, BinaryOperator<T>): kết quả cùng kiểu

~~~java
int product = List.of(2, 3, 4).parallelStream()
        .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
~~~

Chữ ký:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Ở phép nhân, identity là **1**, không phải 0. Nếu dùng 0 thì mọi tích đều bằng 0, kể cả khi các phần tử khác 0.

Nếu gọi `reduce(1, (a,b)->a*b)` trên nguồn rỗng, kết quả là **1**: đây chính là vai trò của phần tử đơn vị. Còn overload không identity trên nguồn rỗng trả Optional.empty.

### 3.3. reduce(identity, accumulator, combiner): phần tử và kết quả khác kiểu

~~~java
int totalLength = List.of("Java", "Go", "C")
        .parallelStream()
        .reduce(
                0,
                (subtotal, word) -> subtotal + word.length(),
                Integer::sum
        );

System.out.println(totalLength); // 7
~~~

Chữ ký tổng quát:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Ở đây:

- Phần tử nguồn **T = String**.
- Kết quả **U = Integer**.
- Identity kiểu U là **0**.
- Accumulator chuyển một **U** và một **String** thành một **U** mới.
- Combiner kết hợp **hai U** từ các nhánh thành một **U**.

Overload này có **hai loại hàm** khác nhau; ngoài associativity của combiner, còn phải kiểm tra luật compatibility giữa accumulator và combiner.

## 4. Phần tử đơn vị (identity) là gì?

Đối với phép kết hợp \(\oplus\), một giá trị e là **phần tử đơn vị hai phía** nếu:

\[
e \oplus x = x
\]

và

\[
x \oplus e = x
\]

với mọi x trong miền giá trị được phép.

Một bảng trực giác:

| Phép kết hợp | Identity | Vì sao |
| --- | --- | --- |
| Cộng số nguyên | **0** | 0 + x = x + 0 = x |
| Nhân số nguyên | **1** | 1 × x = x × 1 = x |
| Nối `String` | **""** | "" + s = s + "" = s |
| AND boolean | **true** | true && x = x && true = x |
| OR boolean | **false** | false &#124;&#124; x = x &#124;&#124; false = x |
| Lấy max trên toàn miền `int` | **Integer.MIN_VALUE** | max(minInt, x) = x |
| Lấy min trên toàn miền `int` | **Integer.MAX_VALUE** | min(maxInt, x) = x |

**Lưu ý về min/max:** một identity hữu hiệu cần hợp lệ với **toàn bộ miền**. Chọn 0 làm identity cho max có thể sai nếu mọi số đều âm. Nếu không có giá trị biên phù hợp hoặc miền không được xác định rõ, dùng `reduce(BinaryOperator)` không identity và trả `Optional`.

### 4.1. Tại sao phải kiểm tra cả trái và phải?

Một số phép toán có identity một phía nhưng không có identity hai phía.

Ví dụ với phép trừ:

~~~text
x - 0 = x           (0 là đơn vị bên phải)
0 - x = -x ≠ x      (0 không là đơn vị bên trái, trừ khi x = 0)
~~~

Do vậy `0` **không** phải identity hai phía của phép trừ.

Test chỉ kiểm tra `combine(x, identity) == x` sẽ bỏ sót lỗi này.

### 4.2. Identity không phải “số cộng thêm ban đầu”

Phản ví dụ:

~~~java
int result = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

Nếu ý định là “10 + tổng [1,2,3]”, cách viết này **không có identity hợp lệ** cho phép cộng. Khi phân hoạch, identity 10 có thể được dùng cho nhiều nhánh.

Cách đúng:

~~~java
int result = 10 + IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // 16
~~~

Như vậy phần bổ sung 10 nằm **ngoài phép reduce**, còn identity của phép cộng vẫn là 0.

### 4.3. Kiểm thử nguồn rỗng là phép thử identity hữu ích

~~~java
int emptySum = IntStream.empty().reduce(0, Integer::sum);
int emptyProduct = IntStream.empty().reduce(1, (a, b) -> a * b);

System.out.println(emptySum);     // 0
System.out.println(emptyProduct); // 1
~~~

Test nguồn rỗng giúp xác nhận giá trị trả về khi không có phần tử, nhưng **chưa chứng minh** identity đúng với mọi giá trị. Phải thử cả hai phía trên nhiều giá trị, nhất là giá trị âm và biên.

## 5. Tính kết hợp (associativity)

Một phép kết hợp \(\oplus\) có tính kết hợp nếu:

\[
(a \oplus b) \oplus c = a \oplus (b \oplus c)
\]

với mọi bộ ba a,b,c trong miền tương ứng.

Điều này cho phép framework thay cách đặt ngoặc mà không làm thay đổi kết quả, một nền tảng của parallel reduction.

### 5.1. Ví dụ phép cộng

~~~text
(2 + 3) + 4 = 9
2 + (3 + 4) = 9
~~~

Trên số nguyên Java, phép cộng `int` là associative theo **semantics wraparound 32-bit**, dù tổng toán học có thể overflow. Vì vậy cần phân biệt:

- **Đúng về hợp đồng reduce trong miền int Java:** phép cộng được xác định với overflow theo modulo 2³².
- **Đúng về nhu cầu nghiệp vụ:** nếu tổng toán học cần chính xác vượt 32-bit, `Integer::sum` có thể cho giá trị không chấp nhận được, bất kể phép toán vẫn associative trong miền int.

Chẳng hạn:

~~~java
int wrapped = Integer.MAX_VALUE + 1;
System.out.println(wrapped); // -2147483648
~~~

Một bài test luật associative **không tự phát hiện** rằng kiểu số được chọn quá nhỏ cho nghiệp vụ.

### 5.2. Phép trừ không có tính kết hợp

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Nếu dùng phép trừ làm accumulator/combiner của reduce song song, các phân hoạch khác nhau có thể dẫn đến các kết quả khác nhau. Cần dùng một thuật toán biểu đạt đúng yêu cầu: chẳng hạn nếu muốn “số đầu trừ tổng những số sau”, hãy tách số đầu và phần còn lại theo một cấu trúc có thứ tự rõ, thay vì kỳ vọng một reduce song song giải thích đúng một phép trừ lần lượt.

### 5.3. Tính kết hợp khác tính giao hoán

**Giao hoán (commutativity)** là:

\[
a \oplus b = b \oplus a
\]

Nó **không** phải điều kiện bắt buộc cho reduce trên **ordered stream**.

Ví dụ phép nối chuỗi:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
"A" + "B" = "AB", nhưng "B" + "A" = "BA"
~~~

Nối String là **associative** nhưng **không commutative**. Trên một ordered stream từ `Stream.of("A","B","C")`, phép rút gọn nối chuỗi đúng hợp đồng cho **"ABC"** dù chạy parallel, miễn các điều kiện reduction được đáp ứng.

Nếu nguồn hoặc phép tổng hợp là **unordered**, không nên áp đặt thứ tự văn bản vốn không được bảo đảm. Với phép không giao hoán, encounter order có thể là một phần quan trọng của yêu cầu.

### 5.4. Phép max/min

`Integer::max` và `Integer::min` là associative. Với các giá trị int, identity cho max/min như bảng phía trên là hợp lệ. Tuy nhiên, khi so sánh object có Comparator, Comparator phải ổn định và tuân thủ luật so sánh; một comparator phụ thuộc trạng thái mutable có thể phá vỡ tính đúng của việc tìm min/max.

## 6. Kiểm thử luật bằng một hàm kiểm tra có thể tái sử dụng

Với một `BinaryOperator<T>`, có thể viết các kiểm tra:

~~~java
static <T> void checkIdentity(
        T identity,
        BinaryOperator<T> combine,
        T value) {
    if (!Objects.equals(combine.apply(identity, value), value)
            || !Objects.equals(combine.apply(value, identity), value)) {
        throw new AssertionError("Invalid identity");
    }
}

static <T> void checkAssociative(
        BinaryOperator<T> combine,
        T a, T b, T c) {
    T left = combine.apply(combine.apply(a, b), c);
    T right = combine.apply(a, combine.apply(b, c));
    if (!Objects.equals(left, right)) {
        throw new AssertionError("Not associative");
    }
}
~~~

Đây là mảnh ghép, cần import `BinaryOperator`, `Objects` và đặt trong lớp. Cách dùng `Objects.equals` phù hợp khi kiểu T có `equals` diễn đạt đúng sự tương đương của kết quả.

**Không tự động áp dụng `Objects.equals` cho mọi kiểu số hoặc kiểu mutable:**

- Với `BigDecimal`, `equals` còn xét **scale**, còn `compareTo` kiểm tra giá trị số; cần chọn khái niệm tương đương theo nghiệp vụ.
- Với `double`, sai số làm tròn khiến kiểm tra bằng nhau tuyệt đối có thể không phù hợp với phép toán gần đúng.
- Với đối tượng mutable, hai nhánh có thể chia sẻ tham chiếu; kiểm tra bằng `equals` trên cùng object bị mutate có thể che giấu lỗi ownership/aliasing.
- Nếu kết quả có các field metadata không liên quan, cần định nghĩa quan hệ tương đương chính xác cho phép rút gọn đó.

### 6.1. Không chỉ test một bộ ba

Một test với `a=1,b=2,c=3` có thể bỏ sót nhiều lỗi. Nên thử:

1. **0**, số dương và số âm.
2. Giá trị trùng nhau.
3. **Integer.MIN_VALUE** và **Integer.MAX_VALUE**.
4. Thứ tự phần tử đảo ngược.
5. Những bộ ba mà cặp trung gian có khả năng tạo overflow.
6. Những giá trị có null hoặc trạng thái thiếu dữ liệu nếu domain cho phép.
7. Bộ ba có cùng khóa so sánh trong bài toán max/min.
8. Dữ liệu ngẫu nhiên có seed cố định để tái hiện phản ví dụ.

Bộ test có thể phát hiện luật bị vi phạm; nó **không thay thế chứng minh** rằng phép kết hợp đúng trên mọi giá trị có thể có.

## 7. Test theo tính chất (property-based test) có seed cố định

Một kỹ thuật hữu ích là tạo nhiều bộ ba a,b,c rồi kiểm tra luật identity và associative.

Pseudo-code:

~~~text
for each value x:
    assert combine(identity, x) == x
    assert combine(x, identity) == x

for each triple (a, b, c):
    assert combine(combine(a, b), c)
        == combine(a, combine(b, c))
~~~

Nếu dùng `Random`, hãy **ấn định seed** và đưa seed vào thông báo lỗi. Khi test thất bại, có thể chạy lại với cùng seed để tái hiện.

Các generator cũng cần có:

- Giá trị biên được thêm tường minh, vì random có thể hiếm khi chọn được chúng.
- Tỷ lệ xuất hiện của số 0 và số âm.
- Dãy dài hơn ba phần tử trong bài test end-to-end.
- Với tổng hợp tài chính, giá trị lớn/số thập phân/số lượng âm nếu business cho phép.

Nên thiết kế thông báo khi fail ghi **cặp/ba giá trị** gây lỗi và **kết quả của hai vế**. Không chỉ in “test failed” vì thiếu dữ liệu để điều tra.

### 7.1. Nhược điểm của chỉ so sequential và parallel

Một phép rút gọn sai luật đôi khi vẫn cho **cùng kết quả** trong vài lượt chạy tuần tự và song song, vì scheduler tình cờ chia dữ liệu theo một cách “đúng” hoặc bộ dữ liệu chưa kích hoạt lỗi.

Vì vậy:

- **Test luật** để kiểm tra nguyên nhân.
- **Test end-to-end** trên sequential/parallel để kiểm tra triển khai.
- **Code review** để tìm alias, mutation và điều kiện tiền đề.
- Không tuyên bố “pass 1.000 lần” là bằng chứng một mutable shared identity an toàn.

## 8. Compatibility trong reduce(identity, accumulator, combiner)

Với overload ba đối số, cần một điều kiện quan trọng khác ngoài identity và associativity của combiner.

Giả sử:

- Identity là e kiểu U.
- Accumulator `acc(U,T)`.
- Combiner `combine(U,U)`.

Điều kiện **compatibility** của Java có thể viết:

\[
combine(u, acc(e,t)) = acc(u,t)
\]

với mọi u,t hợp lệ. Nó bảo đảm việc thêm t vào một subtotal U tương đương tạo subtotal chỉ chứa t từ identity rồi kết hợp.

### 8.1. Ví dụ đúng: tổng độ dài chuỗi

~~~java
int total = Stream.of("Java", "Go", "C")
        .parallel()
        .reduce(
                0,
                (subtotal, word) -> subtotal + word.length(),
                Integer::sum
        );

System.out.println(total); // 7
~~~

Với u=5, t="Go" (độ dài 2):

~~~text
combine(5, acc(0, "Go")) = 5 + 2 = 7
acc(5, "Go")             = 5 + 2 = 7
~~~

Hai vế bằng nhau. Combiner `Integer::sum` associative với identity 0.

### 8.2. Ví dụ sai: combiner không tương thích

~~~java
BiFunction<Integer, String, Integer> accumulator =
        (subtotal, word) -> subtotal + word.length();

BinaryOperator<Integer> badCombiner = Integer::max;
~~~

Với u=3, t="Java":

~~~text
combine(3, acc(0, "Java")) = max(3, 4) = 4
acc(3, "Java")              = 3 + 4 = 7
~~~

Hai vế khác nhau. Mặc dù **max** tự nó associative, nó **không tương thích** với accumulator cộng độ dài.

**Đây là lý do chỉ kiểm tra associativity của combiner chưa đủ cho overload ba đối số.**

### 8.3. Test compatibility

~~~java
static <U, T> void checkCompatibility(
        U identity,
        BiFunction<U, T, U> accumulator,
        BinaryOperator<U> combiner,
        U subtotal,
        T item) {
    U left = combiner.apply(
            subtotal, accumulator.apply(identity, item));
    U right = accumulator.apply(subtotal, item);
    if (!Objects.equals(left, right)) {
        throw new AssertionError("Incompatible reduction");
    }
}
~~~

Đây là mảnh ghép với import `BiFunction`, `BinaryOperator`, `Objects`, đặt trong lớp. Kiểm thử nhiều subtotal U và phần tử T có ý nghĩa. Đừng chỉ kiểm tra subtotal 0: một combiner sai có thể vẫn tình cờ đúng ở giá trị này.

## 9. Identity mutable và aliasing: lỗi mà phép so bằng equals có thể bỏ sót

Một phản ví dụ nguy hiểm:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new ArrayList<String>(),
                (list, word) -> {
                    list.add(word);     // Mutation của identity.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right); // Có thể nhận alias.
                    return left;
                }
        );
~~~

Đây là **phản ví dụ không nên chạy trong production**. Dù code có thể biên dịch, nó vi phạm mô hình của reduce:

- Identity là **một ArrayList mutable**.
- Các nhánh có thể sử dụng cùng đối tượng identity, thay vì mỗi nhánh có một container độc lập.
- Accumulator thay đổi chính list được nhận rồi trả lại cùng tham chiếu.
- Combiner có thể nhận `left == right`, ghép một list với chính nó và nhân bản phần tử.
- ArrayList không thread-safe, nên có thể có race hoặc mất/corrupt dữ liệu.

**Một phép test reduce trên vài phần tử chạy đúng không chứng minh mẫu này hợp lệ.** Việc thêm `synchronizedList` hoặc `AtomicInteger` chỉ tác động tới một phần tính đồng thời, không sửa được identity/aliasing và luật compatibility.

### 9.1. Khi nào dùng collect?

Nếu muốn tạo **danh sách kết quả**, hãy dùng `collect`:

~~~java
List<String> values = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(values); // [A, B, C]
~~~

Ở đây `Supplier` tạo container mới cho quá trình mutable reduction; accumulator cập nhật container của phần công việc; combiner gộp các container riêng theo hợp đồng.

**Không trả cùng một container chung từ Supplier của collect**. Ví dụ `() -> sharedArrayList` là lỗi khác nhưng cùng gốc: phá vỡ quyền sở hữu container khi framework chia công việc.

### 9.2. Kiểm thử mutable result đúng cách

Nếu một phép tổng hợp trả object mutable, không chỉ kiểm tra `result.equals(expected)` một lần. Cần kiểm tra:

- Có tạo **đối tượng riêng** cho mỗi phần công việc khi cần?
- Các kết quả từng phần có thể **alias** nhau không?
- Combiner có bị gọi với cùng object ở cả hai tham số không, và hợp đồng đã cho phép điều đó chưa?
- Sau reduction, nguồn và các object liên quan có bị thay đổi ngoài dự kiến không?
- Với parallel, việc thêm phần tử có an toàn không?
- Trên nhiều phân hoạch, kết quả có đủ phần tử, không nhân đôi, không thiếu không?

**Luật giá trị** và **quyền sở hữu trạng thái** là hai trục kiểm tra riêng.

## 10. Tính kết hợp của double: bài kiểm thử phải biết semantics

Với toán học số thực, phép cộng là associative. Nhưng Java **double** dùng số thực dấu phẩy động IEEE 754, làm tròn sau từng phép toán. Bởi vậy phép cộng double **không associative trong nghĩa bằng bit**.

Ví dụ:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Vế trái: `a+b = 0.0`, cộng c → 1.0.

Vế phải: `b+c` có thể bị làm tròn về -1e16, cộng a → 0.0.

**Hệ quả:** nếu một `DoubleStream.sum()` hoặc reduction song song thay đổi cách nhóm phép cộng, kết quả có thể khác một chút so với thứ tự cộng tuần tự.

### 10.1. Chọn điều kiện so sánh phù hợp

Trong bài toán số đo xấp xỉ, có thể dùng sai số tuyệt đối hoặc tương đối:

~~~java
double tolerance = 1e-9;
if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("Difference too large");
}
~~~

Nhưng **đừng coi đây là công thức phổ quát**:

- Sai số chấp nhận phụ thuộc thang đo và yêu cầu domain.
- `NaN` cần được kiểm tra riêng: mọi so sánh lớn hơn/nhỏ hơn với NaN đều false.
- `Infinity` và overflow có thể khiến sai số mất ý nghĩa.
- Tổng nhiều số khác biệt lớn về độ lớn có thể mất các số hạng nhỏ.
- Nếu bài toán yêu cầu **tính đúng nguyên văn, không sai số**, đổi kiểu số/thuật toán thay vì nới tolerance tùy tiện.

Một test luật associative chính xác theo `Double.equals` sẽ **phát hiện** phản ví dụ trên. Nhưng không nhất thiết nên coi `Double::sum` là phép rút gọn “hoàn toàn vô dụng”: JDK cung cấp các phép tổng hợp double với hợp đồng độ chính xác/giá trị được tài liệu hóa và chúng hữu ích khi nghiệp vụ chấp nhận sai số.

### 10.2. BigDecimal và MathContext

`BigDecimal` là immutable. Phép cộng `BigDecimal::add` không làm tròn nếu không truyền MathContext, nên phù hợp cho một số phép tổng hợp cần độ chính xác thập phân.

~~~java
BigDecimal total = Stream.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"))
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
~~~

Tuy nhiên, khi cộng có **MathContext giới hạn precision** hoặc làm tròn ở từng bước, thứ tự đặt ngoặc có thể ảnh hưởng kết quả. Test luật phải tương ứng đúng cấu hình làm tròn sử dụng ở production.

**Cẩn thận với `BigDecimal.equals`:** ví dụ `new BigDecimal("1.0")` và `new BigDecimal("1.00")` khác `equals` vì scale khác, nhưng bằng nhau theo `compareTo` về giá trị số. Test phải chọn quan hệ tương đương khớp hợp đồng.

## 11. Monoid: mô hình hữu ích để suy nghĩ

Một **monoid** là tập hợp các giá trị với:

1. Phép kết hợp associative.
2. Một phần tử đơn vị hai phía.

Nhiều phép reduce phù hợp với mô hình này:

| Giá trị | Phép kết hợp | Identity |
| --- | --- | --- |
| Integer theo tổng wraparound | `Integer::sum` | 0 |
| Integer theo tích wraparound | `(a,b) -> a*b` | 1 |
| String | `String::concat` | "" |
| Boolean | AND | true |
| Boolean | OR | false |
| Immutable set (theo tập phần tử) | Union tạo tập mới | Tập rỗng |
| BigInteger | `BigInteger::add` | BigInteger.ZERO |

Không cần biết thuật ngữ monoid để viết Java, nhưng nó cung cấp một câu hỏi ngắn gọn: **“Tôi có thể gộp các kết quả từng phần với bất kỳ cách đặt ngoặc nào mà vẫn đúng không?”**

**Không đồng nhất monoid với phép giao hoán.** String concatenation là ví dụ associative với identity nhưng không commutative.

## 12. Chương trình Java 17 kiểm thử luật đầy đủ

Chương trình sau:

- Kiểm tra identity và associativity của **Integer::sum** trên các giá trị biên và **1.000 bộ ba ngẫu nhiên**, seed cố định.
- Kiểm tra identity/associativity của phép nối String trên mọi bộ ba từ một tập mẫu bốn chuỗi.
- Kiểm tra compatibility của reduce ba đối số tính tổng độ dài String trên nhiều subtotal.
- So sánh tổng tuần tự/song song đúng hợp đồng.
- Xác nhận kết quả nguồn rỗng và phép nối chuỗi có encounter order.
- Đưa ra **phản ví dụ** cho phép trừ, combiner sai và phép cộng double không associative.
- Không chạy mẫu reduce dùng mutable identity nguy hiểm.

Tạo file **ReductionLawDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Random;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ReductionLawDemo {
    static <T> void checkIdentity(
            T identity, BinaryOperator<T> operation, T x) {
        T left = operation.apply(identity, x);
        T right = operation.apply(x, identity);
        if (!Objects.equals(left, x)
                || !Objects.equals(right, x)) {
            throw new AssertionError(
                    "Identity failed for " + x);
        }
    }

    static <T> void checkAssociative(
            BinaryOperator<T> operation,
            T a, T b, T c) {
        T left = operation.apply(
                operation.apply(a, b), c);
        T right = operation.apply(
                a, operation.apply(b, c));
        if (!Objects.equals(left, right)) {
            throw new AssertionError(
                    "Associativity failed: " + a + ","
                            + b + "," + c);
        }
    }

    static <U, T> void checkCompatibility(
            U identity,
            BiFunction<U, T, U> accumulator,
            BinaryOperator<U> combiner,
            U partial, T item) {
        U left = combiner.apply(
                partial,
                accumulator.apply(identity, item));
        U right = accumulator.apply(partial, item);
        if (!Objects.equals(left, right)) {
            throw new AssertionError(
                    "Compatibility failed");
        }
    }

    public static void main(String[] args) {
        BinaryOperator<Integer> addition = Integer::sum;
        int[] edgeCases = {
                Integer.MIN_VALUE, -5, -1, 0, 1, 5,
                Integer.MAX_VALUE
        };

        for (int n : edgeCases) {
            checkIdentity(0, addition, n);
        }

        Random random = new Random(0x5EED);
        int intTriples = 1000;

        for (int i = 0; i < intTriples; i++) {
            int a = random.nextInt();
            int b = random.nextInt();
            int c = random.nextInt();
            checkAssociative(addition, a, b, c);
        }
        System.out.println("int law cases: " + intTriples);

        BinaryOperator<String> concat = String::concat;
        List<String> pieces =
                List.of("", "A", "BC", "xyz");
        int stringTriples = 0;

        for (String a : pieces) {
            checkIdentity("", concat, a);
            for (String b : pieces) {
                for (String c : pieces) {
                    checkAssociative(concat, a, b, c);
                    stringTriples++;
                }
            }
        }
        System.out.println(
                "string law cases: " + stringTriples);

        BiFunction<Integer, String, Integer> length =
                (sum, word) -> sum + word.length();
        BinaryOperator<Integer> combiner = Integer::sum;
        List<Integer> partials = List.of(0, 3, 7);
        List<String> words = List.of("", "A", "Java", "Go");

        int compatCases = 0;
        for (int partial : partials) {
            for (String word : words) {
                checkCompatibility(
                        0, length, combiner, partial, word);
                compatCases++;
            }
        }
        System.out.println(
                "three-arg cases: " + compatCases);

        int sequential = IntStream.rangeClosed(1, 1000)
                .reduce(0, Integer::sum);
        int parallel = IntStream.rangeClosed(1, 1000)
                .parallel()
                .reduce(0, Integer::sum);
        if (sequential != 500_500 || parallel != 500_500) {
            throw new AssertionError("Wrong total");
        }
        System.out.println("parallel total: " + parallel);

        int totalLength = words.parallelStream()
                .reduce(0, length, combiner);
        if (totalLength != 7) {
            throw new AssertionError("Wrong word length");
        }
        System.out.println("parallel length: " + totalLength);

        String text = Stream.of("A", "B", "C")
                .parallel()
                .reduce("", String::concat);
        System.out.println("concat: " + text);

        Optional<Integer> noMax =
                Stream.<Integer>empty().reduce(Integer::max);
        System.out.println("max empty: " + noMax.isEmpty());

        BinaryOperator<Integer> subtract = (a, b) -> a - b;
        boolean subtractionIdentity =
                subtract.apply(0, 3) == 3
                        && subtract.apply(3, 0) == 3;
        boolean subtractionAssociative =
                subtract.apply(subtract.apply(10, 3), 2)
                        == subtract.apply(
                                10, subtract.apply(3, 2));
        System.out.println(
                "subtraction identity: " + subtractionIdentity);
        System.out.println(
                "subtraction associative: "
                        + subtractionAssociative);

        BinaryOperator<Integer> wrongCombiner = Integer::max;
        boolean badCompatibility =
                Objects.equals(
                        wrongCombiner.apply(
                                3, length.apply(0, "Java")),
                        length.apply(3, "Java"));
        System.out.println(
                "bad combiner compatible: " + badCompatibility);

        double a = 1e16, b = -1e16, c = 1.0;
        boolean doubleAssociative =
                Double.compare((a + b) + c,
                        a + (b + c)) == 0;
        System.out.println(
                "double associative: " + doubleAssociative);

        System.out.println("all law checks passed");
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac ReductionLawDemo.java
java ReductionLawDemo
~~~

**Đầu ra chính xác:**

~~~text
int law cases: 1000
string law cases: 64
three-arg cases: 12
parallel total: 500500
parallel length: 7
concat: ABC
max empty: true
subtraction identity: false
subtraction associative: false
bad combiner compatible: false
double associative: false
all law checks passed
~~~

### 12.1. Vì sao String có 64 bộ ba?

Tập `pieces` có bốn giá trị. Mỗi vị trí a,b,c có bốn lựa chọn, nên tổng số bộ ba được kiểm thử là:

\[
4 \times 4 \times 4 = 64
\]

Với từng bộ ba, test kiểm tra:

~~~text
concat(concat(a,b),c) == concat(a,concat(b,c))
~~~

Identity `""` cũng được kiểm tra hai phía cho từng giá trị.

### 12.2. Vì sao Integer::sum vượt qua test ngẫu nhiên?

Các phép cộng int dùng semantics 32-bit của Java. Dù có overflow, việc thay nhóm phép cộng **không đổi phần dư 32-bit**. Vì vậy `Integer::sum` có tính kết hợp trong miền giá trị int theo semantics của Java.

Nhưng nếu nghiệp vụ muốn một tổng toán học vượt `Integer.MAX_VALUE`, phải chọn kiểu đủ rộng; các property test trên chỉ xác nhận **luật của phép toán đã chọn**, không kiểm tra giới hạn domain.

### 12.3. Vì sao compatibility có 12 trường hợp?

Có ba subtotal: 0, 3, 7. Có bốn String: "", "A", "Java", "Go". Mỗi cặp `(partial, word)` được kiểm tra một lần, nên có **3 × 4 = 12** trường hợp.

Hàm `length` cộng độ dài String vào subtotal và `combiner` cộng hai subtotal. Hai phép toán tương thích qua identity 0, nên các test đều thành công.

### 12.4. Vì sao subtraction identity và associative đều false?

Với x=3, `0-3=-3` khác 3, nên 0 không là identity hai phía. Với bộ ba (10,3,2), hai cách đặt ngoặc cho 5 và 9. Vì vậy subtraction không đáp ứng luật reduce song song mong muốn.

### 12.5. Vì sao bad combiner compatible false?

Với subtotal=3 và word="Java", accumulator cộng 4. Nhưng combiner `max` chỉ chọn max(3,4)=4, khác `3+4=7`. Dù max riêng lẻ associative, không thể thay combiner cộng bằng max khi accumulator vẫn tính tổng.

### 12.6. Vì sao double associative false?

Số 1e16 quá lớn so với 1.0 để tổng `-1e16 + 1.0` giữ được phần 1.0 với độ chính xác double. Hai thứ tự đặt ngoặc cho 1.0 và 0.0, nên so sánh bằng `Double.compare` nhận false.

### 12.7. Vì sao phần tử max trên stream rỗng không tồn tại?

Overload `reduce(BinaryOperator)` trả Optional. Khi không có identity và nguồn rỗng, kết quả `Optional.empty()`. Điều này giúp không phải chọn một sentinel giả định cho kết quả cực đại.

## 13. Thiết kế kiểm thử đầy đủ theo nhóm lỗi

Một chiến lược QA hiệu quả gồm ba tầng:

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Luật đơn vị** | Identity trái/phải và associativity | `e⊕x=x⊕e=x`; hai cách đặt ngoặc |
| **Luật ghép** | Compatibility của reduce ba đối số | `combine(u,acc(e,t)) == acc(u,t)` |
| **End-to-end** | Semantics trên pipeline và domain | `parallel == sequential` khi có điều kiện đúng; không overflow nghiệp vụ |

Bổ sung các test phạm vi:

- **Nguồn rỗng**: identity hoặc Optional.empty đúng hợp đồng.
- **Một phần tử**: result tương đương phần tử hoặc accumulator(identity, t).
- **Hai, ba, nhiều phần tử**: kiểm tra các phân hoạch khác nhau.
- **Số biên/âm/0**: tránh giả định dữ liệu toàn dương.
- **Định dạng dữ liệu**: String rỗng, Unicode, null nếu API cho phép.
- **Parallel**: chạy với dữ liệu lớn hơn, nhiều cách chia nguồn nhưng không dựa vào scheduler cụ thể.
- **Non-interference**: nguồn không bị sửa bởi các behavioral parameter.
- **Mutable identity**: loại bỏ từ thiết kế, không chỉ “test race”.
- **Sai số**: floating-point và rounding có tiêu chí đánh giá riêng.
- **Lỗi domain**: phép toán thích hợp nhưng kiểu số không đủ miền, hoặc thuật toán không biểu diễn đúng quy tắc kinh doanh.

### 13.1. Không “chứng minh” bằng stress test

Một test race chạy 10.000 lần mà chưa thấy lỗi **không chứng minh** `reduce(new ArrayList<>(), mutate, ...) ` an toàn. Nó có thể chỉ cho thấy cách phân hoạch/chạy trong môi trường test chưa làm lộ lỗi.

Ngược lại, khi review thấy identity mutable được sửa và combiner giả định các đối tượng từng phần độc lập, ta đã có căn cứ lý thuyết để sửa code **trước** khi chạy hệ thống.

### 13.2. Test cho một custom collector khác test cho reduce

Với `collect(supplier, accumulator, combiner)`, mutation **được cho phép trong container được supplier tạo**, nhưng phải tuân thủ các luật của Collector. Cần kiểm tra supplier tạo container độc lập, combiner nối đúng, kết quả không phụ thuộc phân hoạch và các đặc tính `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` nếu tự khai báo.

Không bê một bộ luật `reduce` có identity là object shared rồi coi đó là mô hình cho `collect`; bản chất của mutable reduction là khác.

## 14. Cách tự thiết kế phép rút gọn mới

Trước khi thêm một reducer vào ứng dụng, hãy xác định:

### Bước 1 — Miền giá trị

Kết quả là `int`, `long`, `BigInteger`, `BigDecimal`, `String`, một record immutable hay collection mutable? Có null hay không? Có giới hạn giá trị nào không?

**Không chọn kiểu chỉ vì compiler chấp nhận.** Nếu cần cộng đơn vị tiền lớn, `int` có thể không đủ.

### Bước 2 — Phép kết hợp

Viết biểu thức `combine(a,b)` có ý nghĩa nghiệp vụ. Nó có associative không? Hãy đưa ra lập luận, thử ba giá trị điển hình và giá trị biên.

### Bước 3 — Identity

Tìm e sao cho hai chiều đều đúng. Đừng dùng một seed tùy ý làm identity. Nếu không có identity tự nhiên, cân nhắc overload trả Optional.

### Bước 4 — Accumulator và combiner (nếu ba đối số)

Kiểm tra compatibility:

~~~text
combine(u, accumulator(identity, element))
    == accumulator(u, element)
~~~

Nếu không đúng, sửa logic accumulator/combiner hoặc chọn mô hình thu thập khác.

### Bước 5 — Quyền sở hữu và side effect

Có mutate object chung không? Có sửa nguồn không? Có đọc mutable shared state, thời gian hoặc random không? Nếu có, hãy đổi sang giá trị immutable hoặc tách trách nhiệm ghi dữ liệu khỏi reduction.

### Bước 6 — Test và đánh giá production

Viết test luật, biên, dữ liệu ngẫu nhiên có seed, sequential/parallel và kiểm thử domain. Chỉ sau khi correctness rõ ràng mới benchmark hiệu năng parallel.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Chỉ test một kết quả reduce tuần tự | Chưa kiểm tra chia/gộp | Test identity, associativity và parallel |
| Test identity chỉ một phía | Bỏ sót phép trừ với identity bên phải | Test cả `combine(e,x)` và `combine(x,e)` |
| Dùng seed 10 làm identity phép cộng | Seed có thể áp dụng ở mỗi nhánh | Dùng identity 0, cộng 10 sau reduction |
| Dùng subtraction trong reduce parallel | Không associative | Thiết kế thuật toán khác đúng nghĩa |
| Chỉ test combiner associative ở overload ba đối số | Có thể không tương thích accumulator | Test compatibility |
| Cho rằng max với identity 0 luôn đúng | Sai với tất cả số âm | Dùng min-domain identity hoặc Optional |
| Đồng nhất associative và commutative | Nối chuỗi associative nhưng không commutative | Giữ encounter order khi cần |
| Dùng `ArrayList` mutable làm identity của reduce | Alias và race khi parallel | Dùng collect hoặc kết quả immutable |
| Dùng AtomicInteger/synchronized để “sửa” reduce | Không sửa luật identity/alias | Sửa mô hình phép rút gọn |
| Chỉ kiểm tra `equals` trên cùng mutable object | Aliasing có thể che giấu lỗi | Kiểm tra ownership và snapshot giá trị |
| Dùng `==` cho double gần đúng | Rounding phụ thuộc thứ tự | Dung sai có cơ sở hoặc kiểu số chính xác |
| Thấy Integer::sum associative nên tin tổng không overflow | Luật modulo khác nhu cầu kinh doanh | Chọn kiểu số đủ miền |
| Dùng BigDecimal.equals mà yêu cầu chỉ so giá trị số | Scale khác nhau có thể làm test fail | Dùng compareTo khi phù hợp |
| Tuyên bố pass random test nghĩa là chứng minh đúng | Test chỉ lấy mẫu hữu hạn | Kết hợp lập luận luật và kiểm thử |
| Quên test rỗng/một phần tử | Bỏ sót identity/sentinel sai | Test biên bắt buộc |
| Bật parallel với mapper/stateful side effect | Kết quả phụ thuộc lịch chạy | Stateless/non-interfering operations |

## 16. Bài tập thực hành

### Bài 1 — Identity của max

Có một Stream<Integer> có thể chứa số âm. Có đúng khi gọi `reduce(0, Integer::max)` không?

**Đáp án:** không đúng trên toàn miền int. Với nguồn chỉ gồm -5 và -2, max thật là -2 nhưng kết quả với identity 0 là 0. Dùng `reduce(Integer::max)` trả Optional<Integer>, hoặc `reduce(Integer.MIN_VALUE, Integer::max)` nếu cần identity phù hợp với toàn miền.

### Bài 2 — Dự đoán phản ví dụ phép trừ

~~~java
BinaryOperator<Integer> subtract = (a, b) -> a - b;
~~~

Hãy tính `(10 - 3) - 2` và `10 - (3 - 2)`.

**Đáp án:** 5 và 9. Phép trừ không associative và 0 không là identity hai phía.

### Bài 3 — Kiểm tra nối chuỗi

Với `String::concat` và identity `""`, hãy kiểm tra cả hai phía và associativity trên `"A", "B", "C"`. Có commutative không?

**Đáp án:** identity và associative đúng theo nội dung; không commutative vì `"AB"` khác `"BA"`. Với ordered stream và reducer đúng hợp đồng, ghép theo encounter order cho kết quả "ABC".

### Bài 4 — Sửa combiner sai

Một API tính tổng độ dài String bằng accumulator:

~~~java
(sum, word) -> sum + word.length()
~~~

nhưng dùng combiner `Integer::max`. Hãy chỉ ra bộ `u=3, t="Java"` làm hỏng compatibility.

**Đáp án:** `max(3,4)=4` khác `3+4=7`. Dùng `Integer::sum` làm combiner.

### Bài 5 — Sửa reduce mutable

Mã cũ dùng `reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)`. Tại sao không dùng trên parallel stream? Viết lại bằng `collect`.

**Gợi ý:**

~~~java
String result = words.parallelStream()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();
~~~

Với nguồn ordered, kết quả giữ thứ tự theo semantics của collector khi hợp đồng được đáp ứng. Supplier tạo các builder riêng cho mutable reduction thay vì chia sẻ một identity mutable trong reduce.

### Bài 6 — Kiểm tra phép cộng số thực

Tại sao `(1e16 + (-1e16)) + 1.0` khác `1e16 + ((-1e16) + 1.0)` trong double?

**Đáp án:** do mất độ chính xác khi cộng số rất lớn và rất nhỏ; thứ tự làm tròn tạo kết quả 1.0 và 0.0. Không áp dụng giả định associative toán học nguyên xi cho double nếu test yêu cầu bằng bit.

### Bài 7 — Thiết kế bộ property test

Viết vòng lặp sinh 1.000 bộ ba int với seed cố định, test identity 0 và associativity của Integer::sum. Bổ sung kiểm tra các giá trị MIN/MAX.

**Gợi ý:** chương trình phần 12 có thể làm mẫu. Nếu đổi sang custom reducer, thêm thông báo lỗi chứa ba giá trị và hai vế để dễ tái hiện.

### Bài 8 — Kiểm tra nghiệp vụ

Một hệ thống tính tổng doanh thu, mỗi giao dịch có amount theo đơn vị nhỏ nhất. Phép cộng int thỏa luật trong modulo 32-bit, nhưng kết quả tổng có thể overflow. Cần test nào ngoài identity/associativity?

**Đáp án:** test miền giá trị/overflow và lựa chọn kiểu (long, BigInteger, BigDecimal) đúng quy tắc đơn vị/rounding. Tính đúng đại số của reduce không thay thế tính đúng nghiệp vụ.

## 17. Ghi nhớ

Một phép rút gọn đáng tin không chỉ “cho đúng kết quả trên một danh sách nhỏ”. Với `Stream.reduce()`, hãy xác minh:

- **Identity hai phía:** `combine(identity,x)==x` và `combine(x,identity)==x`.
- **Associativity:** `combine(combine(a,b),c)==combine(a,combine(b,c))`.
- **Compatibility** cho overload ba đối số: `combine(u,acc(identity,t))==acc(u,t)`.
- **Stateless/non-interfering:** không dựa vào biến mutable chia sẻ, không mutate nguồn hoặc một identity mutable.
- **Đúng kiểu và domain:** xử lý overflow, sai số, null, quy tắc tiền tệ và quan hệ tương đương.
- **Kiểm thử đa tầng:** giá trị biên, random seed cố định, trường hợp rỗng/một phần tử và sequential/parallel.
- **Không đòi commutativity nếu chỉ cần associativity**, nhưng phải chú ý encounter order khi phép kết hợp không giao hoán.

Dùng **reduce** cho phép kết hợp giá trị đúng hợp đồng; dùng **collect** khi cần mutable accumulation có quyền sở hữu container rõ ràng. Luật đại số giúp bạn biết **vì sao phép rút gọn đúng**, còn kiểm thử nhiều tầng giúp phát hiện sai sót triển khai và những yêu cầu nghiệp vụ vượt ngoài luật đó.
