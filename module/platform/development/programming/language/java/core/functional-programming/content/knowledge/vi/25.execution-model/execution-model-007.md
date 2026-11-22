# Pipeline không có tác dụng phụ bắt buộc khi JDK tối ưu bỏ bước

## 1. Khi gọi terminal operation, có phải mọi lambda đều chạy?

Một trực giác phổ biến khi học Stream là: **“Tôi đã viết một bước `map` hoặc `peek` thì terminal operation chắc chắn chạy bước đó cho từng phần tử.”** Đây là cách suy luận **không đúng theo hợp đồng Java Stream**.

Xét đoạn mã:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long count = names.stream()
        .peek(System.out::println)
        .count();
System.out.println("count=" + count);
~~~

Đây là mã minh họa trong một phương thức; cần `import java.util.List;`. Một số người dự đoán chương trình sẽ in ba tên rồi in `count=3`. Nhưng với JDK có khả năng suy ra cardinality của List, lời gọi `count()` **có thể trả ngay 3 mà không duyệt từng phần tử**, vì `peek` không thay đổi số lượng. Khi đó không có tên nào được in.

Tương tự, nếu một `map` chỉ đổi mỗi phần tử thành một giá trị khác nhưng vẫn giữ **một đầu ra cho một đầu vào**, việc chạy mapper có thể không cần thiết để tìm số lượng:

~~~java
long count = names.stream()
        .map(String::toUpperCase)
        .count();
// 3, và việc tạo chuỗi chữ hoa có thể bị bỏ qua.
~~~

Đây **không phải lỗi JDK**, cũng không phải bản chất `peek` luôn vô dụng. **Stream mô tả cách tính kết quả**, chứ không phải danh sách những lệnh bắt buộc phải thực hiện ở mọi cấu hình. Nếu implementation chứng minh được việc bỏ qua một phần pipeline **không đổi kết quả được yêu cầu**, nó có quyền bỏ qua cả việc gọi các hàm được gắn với bước đó.

Theo tài liệu Java SE 17 về side effects, các tác dụng phụ của behavioral parameters nói chung **không được bảo đảm luôn xảy ra**, ngoại trừ những hợp đồng đặc biệt được nêu rõ, điển hình là action của terminal operations `forEach` và `forEachOrdered`.

**Thông điệp chính:** Đừng ẩn **validation bắt buộc, lưu dữ liệu, gửi thông báo hoặc cập nhật trạng thái nghiệp vụ** bên trong `map`/`peek` rồi dùng một terminal operation không cần những giá trị biến đổi để hy vọng chúng sẽ được thực thi.

## 2. Hiểu cấu trúc pipeline trước khi bàn tối ưu

Một Stream pipeline gồm ba phần:

~~~text
NGUỒN                    TRUNG GIAN                       KẾT THÚC
List / Set / array  ->   filter / map / peek / sorted  ->   count / toList / sum
                            (intermediate operations)       (terminal operation)
~~~

- **Nguồn** cung cấp phần tử theo hợp đồng riêng. Ví dụ List thường có encounter order và biết số lượng.
- **Intermediate operations** mô tả việc tạo một Stream mới; đa số không xử lý phần tử ngay khi được gọi. Tài liệu JDK mô tả chúng là **lazy**.
- **Terminal operation** yêu cầu một kết quả hoặc một hành động. Nó có thể duyệt toàn bộ, duyệt một phần, hoặc **không cần duyệt** nếu kết quả được suy ra bằng cách khác.

Ví dụ:

~~~java
Stream<String> pipeline = names.stream()
        .filter(s -> s.length() > 2)
        .map(String::toUpperCase);

// Chỉ từ đây mới có yêu cầu hoàn tất một kết quả:
List<String> result = pipeline.toList();
~~~

Đoạn này cần import `java.util.stream.Stream`, `java.util.List` và biến `names`. Khi tạo `pipeline`, việc lọc và ánh xạ chưa cần chạy. Khi gọi `toList()`, giá trị từng chuỗi kết quả cần được tạo để dựng danh sách, nên các phép tính ảnh hưởng đến giá trị đó được đánh giá theo yêu cầu của pipeline.

### 2.1. Ba hiện tượng khác nhau thường bị gọi chung là “bỏ bước”

| Hiện tượng | Tại sao không chạy mọi callback? | Ví dụ |
| --- | --- | --- |
| **Lazy evaluation** | Chưa gọi terminal operation | `stream.map(f)` rồi chưa dùng |
| **Short-circuiting** | Đã đủ thông tin để kết thúc sớm | `anyMatch` gặp phần tử phù hợp |
| **Elision/optimization** | Một bước hoặc toàn pipeline không cần thiết cho kết quả | `List.stream().peek(action).count()` |

Các hiện tượng có thể kết hợp, nhưng nguyên nhân khác nhau. Chẳng hạn `findFirst()` có thể dừng sau phần tử đầu mà không đánh giá các phần tử còn lại; `count()` trên nguồn có kích thước đã biết thậm chí có thể không cần **bắt đầu traversal**.

Điều người lập trình cần kiểm tra là **kết quả mà terminal operation cam kết**, không phải mong đợi rằng mọi lambda trung gian chạy đủ số lần rồi mới có kết quả.

## 3. Hợp đồng tối ưu hóa của Stream trong Java 17

Tài liệu `Stream<T>` cho phép implementation tối ưu cách tính và loại bỏ những operation hoặc stage nếu chứng minh việc loại bỏ **không ảnh hưởng kết quả phép tính**. Hệ quả là các behavioral parameters — các lambda/method reference do lập trình viên cung cấp cho operator — có thể không được gọi.

Java SE 17 cũng lưu ý rằng, khi behavioral parameters có tác dụng phụ, nói chung không có bảo đảm về:
- **Việc tác dụng phụ luôn xảy ra**, vì bước có thể bị bỏ qua.
- **Thời điểm và thứ tự tác dụng phụ** so với những tác dụng phụ khác, nhất là ở Stream song song.
- **Thread nào thực thi callback** cho một phần tử, hoặc các bước trên cùng phần tử có được thực thi bởi cùng thread không.
- **Khả năng thread khác nhìn thấy tác dụng phụ** nếu không dùng cơ chế đồng bộ đúng hợp đồng.

Các điểm này là lý do Java khuyến khích callback trong phần lớn Stream operations phải **stateless** và **non-interfering**.

### 3.1. Stateless

Một hàm stateless không dựa vào trạng thái mutable bên ngoài có thể thay đổi trong quá trình pipeline. Ví dụ tốt:

~~~java
List<Integer> squares = List.of(2, 3, 4).stream()
        .map(n -> n * n)
        .toList();
// [4, 9, 16]
~~~

Mapper chỉ phụ thuộc `n` và trả một giá trị mới. Nếu framework đổi lịch xử lý hoặc chia nhóm, ý nghĩa dữ liệu vẫn rõ.

Phản ví dụ:

~~~java
// KHÔNG NÊN dùng trạng thái ngoài để tính giá trị trong pipeline:
// int[] counter = {0};
// List<Integer> result = numbers.parallelStream()
//         .map(n -> n + counter[0]++)
//         .toList();
~~~

Đoạn phản ví dụ được comment vì sự thay đổi `counter` khiến giá trị của `map` phụ thuộc thứ tự và thread; trong parallel stream còn có race. Ngay cả khi thử tuần tự thấy đúng, không thể lấy kết quả đó làm hợp đồng an toàn để tùy ý chuyển sang parallel.

### 3.2. Non-interfering

Một lambda non-interfering không sửa nguồn Stream đang được duyệt. Ví dụ cần tránh:

~~~java
// KHÔNG AN TOÀN: sửa cấu trúc nguồn trong lúc đang stream.
// List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
// values.stream().forEach(v -> values.add(v * 10));
~~~

Việc sửa List trong lúc traversal có thể gây `ConcurrentModificationException` hoặc hành vi ngoài mong đợi. Không phải mọi vi phạm đều nhất thiết được báo bằng exception. Để tạo dữ liệu mới, dùng transformation + terminal operation phù hợp thay vì sửa nguồn ngay trong callback.

### 3.3. Tối ưu không phải giấy phép thay đổi kết quả

JDK được phép bỏ qua bước **chỉ khi không đổi kết quả theo hợp đồng của pipeline**. Ví dụ:

~~~java
List<String> transformed = List.of("A", "BB").stream()
        .map(String::toLowerCase)
        .toList();
~~~

Kết quả được yêu cầu là `[a, bb]`. Không thể tự bỏ phép đổi chữ thường rồi trả `[A, BB]` mà vẫn nói là tối ưu hợp lệ. Trái lại, nếu terminal operation chỉ yêu cầu **số lượng**, những giá trị chữ thường trung gian có thể không cần được tạo.

**Phân biệt:** “mapper có thể không được gọi trong một pipeline” không đồng nghĩa “JDK có thể trả một kết quả sai”. Giá trị của callback cần cho kết quả thì phải được xử lý theo đúng ngữ nghĩa; những tác dụng phụ bên ngoài kết quả mới là điểm không nên dựa vào.

## 4. Trường hợp điển hình: count() và nguồn biết kích thước

`Stream.count()` trả số phần tử của Stream cuối. Nó có thể tính số lượng từ metadata của nguồn, nhất là khi nguồn có kích thước chính xác và các bước trung gian không đổi cardinality.

Một số `Spliterator` có đặc tính `SIZED`, giúp JDK biết kích thước chính xác theo hợp đồng. Collection thông dụng như List có thể cung cấp kích thước mà không phải duyệt từng phần tử.

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long total = names.stream()
        .map(String::toUpperCase)
        .count();
// total == 3
~~~

Vì `map` là phép **một đầu vào → một đầu ra**, không cần gọi `String::toUpperCase` để biết vẫn có ba phần tử.

Tương tự:

~~~java
AtomicInteger counter = new AtomicInteger();

long total = names.stream()
        .peek(s -> counter.incrementAndGet())
        .count();
~~~

Đoạn minh họa cần import `java.util.concurrent.atomic.AtomicInteger`. Trên JDK 17 trong kiểm thử của bài, `total=3` và `counter.get()=0`; hành vi này là một ví dụ tối ưu hợp lệ, không phải con số callback được hứa cho mọi phiên bản.

### 4.1. Vì sao peek không bắt buộc được gọi?

`peek(action)` là intermediate operation chuyên dùng để **quan sát phần tử khi phần tử thực sự đi qua**. Nó không thêm hoặc loại phần tử, nên kết quả đếm có thể không cần tới action của `peek`.

API Note của `count()` minh họa ngay tình huống List có kích thước biết trước và `peek(System.out::println)`: JDK có thể trả số lượng mà không xử lý pipeline, vì nội dung in ra không ảnh hưởng đến kết quả count.

Không diễn giải `peek` thành:
- Một “trigger” bắt buộc cho từng phần tử.
- Một phép validation có tính bắt buộc.
- Một bước lưu/ghi dữ liệu đảm bảo thành công.
- Một công cụ đếm số phần tử đã được xử lý đáng tin cậy bằng side effect.

`peek` chủ yếu phù hợp với **debugging tạm thời** hoặc quan sát không thiết yếu. Ngay cả khi thấy log trong một lần chạy, đừng suy ra lần chạy tiếp theo hoặc terminal operation khác phải giống vậy.

### 4.2. map().count() có thể không ném exception trong mapper

Giả sử mapper chứa kiểm tra dữ liệu:

~~~java
static int validateAndMeasure(String value) {
    if (value.equals("BB")) {
        throw new IllegalArgumentException("Invalid BB");
    }
    return value.length();
}
~~~

Phương thức minh họa này phải được khai báo trong một class. Lời gọi:

~~~java
long count = List.of("A", "BB", "CCC").stream()
        .map(MyClass::validateAndMeasure)
        .count();
~~~

Là **đoạn minh họa**, tên `MyClass` giả định là class chứa phương thức. Trong pipeline với List biết số lượng, mapper không đổi số phần tử. JDK có thể trả `count=3` **mà không gọi validation**; exception từ `"BB"` vì thế **không nhất thiết xuất hiện**.

Đừng biến đặc điểm này thành lời hứa “map() sẽ không bao giờ ném lỗi khi kết thúc bằng count()”. Nếu nguồn khác hoặc có bước trung gian khác khiến giá trị phải đánh giá, mapper có thể chạy và ném lỗi. **Cả hai tình huống đều chỉ ra rằng thiết kế dựa vào exception trong mapper để validate trước count là không an toàn.**

### 4.3. Các thao tác thay đổi cardinality

Một phép đếm không thể tự suy ra chỉ từ kích thước nguồn nếu pipeline có bước làm số lượng phụ thuộc dữ liệu. Ví dụ:

~~~java
long result = List.of("A", "BB", "CCC", "DDDD").stream()
        .filter(s -> s.length() > 2)
        .count();
// 2
~~~

`filter` giữ lại `CCC` và `DDDD`. Số phần tử đầu ra cần biết predicate đúng với phần tử nào, không thể tự lấy kích thước List là 4 rồi trả kết quả 4.

Các thao tác thường ảnh hưởng cardinality gồm `filter`, `flatMap`, `distinct`, `mapMulti`, `takeWhile` và `dropWhile`. Các thao tác `skip` và `limit` có thể thay đổi số lượng nhưng trong một pipeline đơn giản trên nguồn đã biết kích thước, cardinality sau chúng có thể được tính bằng công thức trực tiếp.

| Bước | Có giữ số phần tử theo ngữ nghĩa không? | Hệ quả với count |
| --- | --- | --- |
| `map(f)` | Có, một vào/một ra | Có thể bỏ qua việc tính f |
| `peek(action)` | Có | Có thể bỏ qua action |
| `sorted()` | Có | Thứ tự không ảnh hưởng số phần tử |
| `filter(predicate)` | Không nhất thiết | Kết quả thường phụ thuộc dữ liệu |
| `flatMap(f)` | Không; một phần tử có thể sinh nhiều phần tử | Thường cần xác định số phần tử sinh ra |
| `distinct()` | Không; phần tử trùng có thể bị loại | Số kết quả phụ thuộc dữ liệu hoặc thuộc tính nguồn |
| `limit(n)` | Có thể cắt bớt | Có thể suy số lượng nếu biết kích thước trước đó |
| `skip(n)` | Có thể bỏ bớt | Có thể suy số lượng nếu biết kích thước trước đó |

Bảng phản ánh cơ hội tối ưu **theo ngữ nghĩa**, không bảo đảm JDK sẽ áp dụng một cách thực thi cụ thể với mọi nguồn/phiên bản. Khi dùng `filter`, JDK thường phải xét predicate để tính cardinality, nhưng **không nên dùng số lần gọi predicate** như một bộ đếm side-effect được bảo đảm riêng khỏi kết quả.

## 5. Phân biệt “bước bị tối ưu bỏ” và “bước chưa tới vì dừng sớm”

Lấy Stream có thứ tự:

~~~java
List<String> words = List.of("A", "BB", "CCC", "DDDD");
boolean found = words.stream()
        .anyMatch(s -> s.equals("A"));
~~~

`anyMatch` chỉ cần biết **có ít nhất một phần tử thỏa**. Ngay khi đủ thông tin, pipeline tuần tự có thể trả `true` và không cần xét các phần tử tiếp theo.

Một ví dụ có bộ đếm để khảo sát:

~~~java
AtomicInteger inspected = new AtomicInteger();

boolean found = words.stream().anyMatch(s -> {
    inspected.incrementAndGet();
    return s.equals("A");
});
~~~

Trong chương trình Java 17 ở phần 9, `found=true` và `inspected.get()=1`. Đây là kết quả đã kiểm chứng trên pipeline tuần tự cụ thể. Điểm bản chất không phải “anyMatch luôn gọi đúng một lần”, mà là **terminal operation này có thể dừng trước khi gọi predicate với mọi phần tử**.

Các thao tác thường liên quan short-circuit:
- `findFirst()`, `findAny()`: có thể dừng khi tìm được một phần tử phù hợp theo hợp đồng.
- `anyMatch()`: có thể dừng khi tìm được một phần tử khớp.
- `allMatch()`: có thể dừng khi tìm được một phần tử không khớp.
- `noneMatch()`: có thể dừng khi tìm được một phần tử khớp.
- `limit(n)`: có thể hạn chế số phần tử đi xa hơn trong pipeline.

Với Stream song song, nhiều phần tử có thể đã hoặc đang được đánh giá khi kết quả đủ để kết thúc; không được dựa vào **số callback chính xác** hay **vị trí cuối cùng đã xử lý** để làm hợp đồng nghiệp vụ.

### 5.1. findFirst và peek có thể chỉ quan sát một phần

~~~java
Optional<String> first = words.stream()
        .peek(System.out::println)
        .findFirst();
~~~

Đoạn minh họa cần import `java.util.Optional`. Với List tuần tự không rỗng, tìm phần tử đầu không cần kiểm tra phần tử còn lại. `peek` có thể chỉ quan sát phần tử thực sự đi qua; những phần tử phía sau không phải được in đầy đủ chỉ vì bạn đã viết `peek`.

Ngay cả khi `findFirst` cam kết chọn phần tử đầu theo encounter order, **thứ tự giá trị đầu ra** không phải là cam kết mọi callback trung gian chạy theo một lịch duyệt nhất định.

### 5.2. limit và skip cũng không phải bộ đếm số lần thực thi

~~~java
long count = words.stream()
        .skip(1)
        .limit(2)
        .peek(System.out::println)
        .count();
~~~

Kết quả đếm là 2. Với nguồn List biết kích thước, JDK có thể tính số phần tử còn lại sau skip/limit **mà không in ra hai phần tử**. Vì vậy, ngay cả `limit(2)` cũng không chứng minh hai callback `peek` đã thực thi.

**Cardinality của kết quả** và **số lần thực thi các hành động phụ** là hai đại lượng khác nhau.

## 6. Terminal operations nào thực sự dành cho tác dụng phụ?

Tài liệu Stream nêu ngoại lệ quan trọng đối với việc bỏ qua tác dụng phụ: **action của `forEach` và `forEachOrdered`** là phần của hợp đồng terminal operation, thay vì chỉ là side effect ngoài mục tiêu của một phép tính số lượng.

~~~java
List<String> words = List.of("A", "BB", "CCC");
words.stream()
        .map(String::toLowerCase)
        .forEachOrdered(System.out::println);
~~~

Với nguồn List tuần tự, kết quả được in:

~~~text
a
bb
ccc
~~~

Ở đây terminal operation **yêu cầu thực hiện action** trên các phần tử đi đến nó, nên không thể đơn giản bỏ qua toàn bộ action rồi cho rằng nó đã đáp ứng hợp đồng. Dĩ nhiên, exception trong quá trình duyệt có thể ngắt phép xử lý và các bước ở trước vẫn chịu điều kiện phù hợp của Stream API.

### 6.1. forEach và forEachOrdered khác gì?

| Terminal operation | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `forEach(action)` | Thực hiện action cho các phần tử của Stream | Với parallel stream, không bảo đảm thứ tự action |
| `forEachOrdered(action)` | Thực hiện action theo encounter order nếu Stream có thứ tự | Có thể hạn chế mức song song; không đồng nghĩa tất cả action luôn chạy trên một thread |
| `toList()` | Tạo danh sách kết quả của pipeline | Tác dụng phụ trong các callback trung gian không phải mục tiêu/đảm bảo riêng của API |
| `count()` | Trả cardinality | Có thể không cần duyệt/callback trung gian |

Nếu công việc thực sự là **ghi một kết quả cho từng phần tử**, một vòng lặp tường minh hoặc `forEach` là cách biểu đạt hành động rõ hơn `peek` hoặc `map(...).count()`. Nếu công việc cần thứ tự, xác định rõ encounter order và chọn `forEachOrdered` hoặc vòng lặp phù hợp.

### 6.2. “Action được gọi” không đồng nghĩa “giao dịch thành công”

Lời gọi `forEach(repository::save)` có nghĩa hành động lưu được yêu cầu cho từng phần tử được duyệt trong execution hoàn tất thành công. Nhưng:
- Nếu một action ném exception, quá trình có thể kết thúc trước khi xử lý những phần tử còn lại.
- Những lưu trữ đã thành công trước lỗi không tự bị rollback.
- Retry toàn bộ có thể tạo bản ghi lặp nếu thao tác không idempotent.
- Trong parallel stream, phải tự xem xét thread safety và giới hạn concurrency của tài nguyên bên ngoài.
- `forEach` không hứa thứ tự với parallel stream; `forEachOrdered` giữ thứ tự action theo nguồn có encounter order, nhưng không biến việc lưu nhiều đối tượng thành một transaction.

Nếu nghiệp vụ đòi hỏi **all-or-nothing**, cần transaction hoặc cơ chế commit/compensation độc lập; không thể chỉ chọn terminal operation rồi suy ra bảo đảm nguyên tử.

## 7. Cách viết sai và cách viết đúng theo mục tiêu

### 7.1. Sai: dùng map() để lưu dữ liệu rồi gọi count()

~~~java
// KHÔNG DÙNG ĐỂ BẢO ĐẢM ĐÃ LƯU MỌI PHẦN TỬ:
// long saved = orders.stream()
//         .map(order -> {
//             repository.save(order);
//             return order;
//         })
//         .count();
~~~

Đây là **phản ví dụ có các tên biến giả định**; chương trình bên trên được comment và không phải file chạy độc lập. `map` giữ cardinality; nếu nguồn biết kích thước, `count` có thể hoàn tất mà không gọi `repository.save`. Kết quả `saved` vì thế có thể chỉ là **số phần tử của Stream**, không phải số lần ghi thực sự được thực hiện thành công.

Cách làm rõ ý định:

~~~java
// Minh họa mô hình hành động:
// for (Order order : orders) {
//     repository.save(order);
// }
~~~

Hoặc, khi đã quyết định theo hợp đồng và kiểm soát được lỗi/side effects:

~~~java
// orders.stream().forEach(repository::save);
~~~

Các tên `Order`, `orders`, `repository` là giả định. Trong production, cần thiết kế boundary transaction, xử lý exception, logging và idempotency. Mục đích là **đặt tác dụng phụ ở bước hành động được yêu cầu**, không giấu nó trong một mapper mà kết quả không cần dùng.

### 7.2. Sai: validate bằng map() rồi count()

~~~java
// KHÔNG ĐÁNG TIN CẬY:
// long count = inputs.stream()
//         .map(x -> {
//             validateOrThrow(x);
//             return x;
//         })
//         .count();
~~~

Nếu tất cả phần tử phải được xác thực trước khi commit, cách này không phù hợp: bước `map` có thể không chạy. Cần đưa validation vào một quy trình có **kết quả phụ thuộc vào validation**.

Nếu chỉ cần đếm phần tử hợp lệ:

~~~java
long validCount = inputs.stream()
        .filter(this::isValid)
        .count();
~~~

Đây là mã minh họa trong instance method có `inputs` và `isValid` được định nghĩa. Kết quả đếm phụ thuộc predicate. Tuy nhiên, **đếm hợp lệ** khác với **bắt buộc báo đủ lỗi của mọi phần tử** hoặc **từ chối toàn lô**. Hãy chọn đúng hợp đồng.

Nếu muốn phản hồi chi tiết từng phần tử, biến kết quả validation thành dữ liệu:

~~~java
record Check(String input, boolean valid) {}

List<Check> checks = inputs.stream()
        .map(input -> new Check(input, isValid(input)))
        .toList();
~~~

Đoạn minh họa này gồm khai báo record tại cấp kiểu và lời gọi trong phương thức. Với pipeline cần dựng `List<Check>`, các kết quả `Check` chứa thông tin validation là **một phần của giá trị đầu ra**, không phải chỉ là side effect của mapper trước `count()`. Nếu cần cả mã lỗi và vị trí, mở rộng record thành một kết quả `Success/Failure` theo domain.

### 7.3. Sai: dùng peek() làm audit log bắt buộc

~~~java
// KHÔNG BẢO ĐẢM LOG ĐỦ MỌI PHẦN TỬ:
// long total = events.stream()
//         .peek(auditLog::write)
//         .count();
~~~

Nếu `count()` không cần duyệt, audit log có thể thiếu toàn bộ. Nếu pipeline kết thúc sớm, log có thể chỉ ghi cho một phần. Một **audit log bắt buộc** nên được thiết kế như một thao tác được quản lý rõ trong workflow, có quy tắc xác nhận lưu thành công, retry/idempotency và xử lý lỗi.

Nếu chỉ muốn quan sát dữ liệu khi đang debug, `peek` là công cụ phù hợp hơn; vẫn phải hiểu rằng nó chỉ quan sát những phần tử thực sự được xử lý.

### 7.4. Sai: tích lũy bằng biến ngoài trong map/forEach song song

~~~java
// KHÔNG AN TOÀN:
// List<String> output = new ArrayList<>();
// source.parallelStream().forEach(output::add);
~~~

`ArrayList` không an toàn cho nhiều ghi đồng thời. Hãy để framework quản lý kết quả:

~~~java
List<String> output = source.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

Đây là mã minh họa với `source` là Collection chuỗi. Kết quả `toList()` được xây dựng theo hợp đồng Stream; các callback không tự ý ghi vào một danh sách mutable dùng chung. Nếu cần gom nhóm/tính tổng, dùng `collect(Collector)` hoặc `reduce(...)` với hợp đồng phù hợp.

## 8. Trong parallel stream, tác dụng phụ còn khó dự đoán hơn

Một pipeline song song có thể xử lý những phần tử ở các thread và thời điểm khác nhau. Kể cả khi kết quả cuối của một ordered stream có thứ tự xác định, **thứ tự gọi mapper hoặc predicate không được hứa giống encounter order**.

Ví dụ:

~~~java
List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 10)
        .toList();
// [10, 20, 30, 40]
~~~

Kết quả được sắp theo encounter order của nguồn List vì `toList()` có hợp đồng phù hợp, nhưng không được suy ra mapper đã chạy lần lượt 1, 2, 3, 4.

### 8.1. Đừng dựa vào thứ tự log

~~~java
// Không dùng thời điểm log làm bằng chứng thứ tự xử lý:
// List<Integer> result = numbers.parallelStream()
//         .peek(n -> System.out.println("Processing " + n))
//         .map(n -> n * 10)
//         .toList();
~~~

Các dòng `println` có thể bị xen kẽ hoặc xảy ra ở nhiều thread; với những pipeline/terminal khác, `peek` có thể không chạy cho một số phần tử hoặc bị loại bỏ. Nếu yêu cầu là một nhật ký theo thứ tự, hãy tổ chức ghi log tại boundary có thể kiểm soát thứ tự, thay vì suy từ thứ tự gọi callback.

### 8.2. Đồng bộ hóa không sửa được thiếu bảo đảm invocation

Dùng `AtomicInteger` thay `int[]` có thể giúp phép tăng đếm an toàn trước data race trong một số trường hợp. Nhưng **atomicity không bắt JDK phải gọi callback**. Ví dụ `peek(counter::incrementAndGet).count()` vẫn có thể trả cardinality mà bộ đếm không tăng.

Do đó có hai câu hỏi độc lập:
1. Nếu callback chạy song song, tác dụng phụ có an toàn và nhìn thấy được không?
2. Callback **có được yêu cầu phải chạy** theo hợp đồng terminal operation không?

Trả lời “có” cho câu hỏi thứ nhất **không** tự trả lời câu hỏi thứ hai.

### 8.3. Exception và việc hủy

Một exception trong callback được thực thi có thể làm terminal operation thất bại; các tác dụng phụ đã xảy ra trước đó không tự rollback. Với parallel stream, các tác vụ khác có thể đã bắt đầu hoặc thực hiện một phần công việc trước khi lỗi lan về caller. Đừng coi exception là một công cụ “hủy tất cả thread ngay lập tức” hoặc một giao dịch hoàn tác.

Nếu có API gửi email, thanh toán hay ghi dữ liệu, cần thiết kế thao tác ngoài Stream hoặc một lớp xử lý có quy tắc rollback/compensation và idempotency cụ thể.

## 9. Chương trình Java 17 hoàn chỉnh và kết quả quan sát

Tạo file **StreamSideEffectOptimizationDemo.java**. Ví dụ deliberately dùng `AtomicInteger` để **quan sát số lần callback trong lần chạy**, không khuyến nghị dùng counter này làm một phần business logic.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class StreamSideEffectOptimizationDemo {
    static int validateAndMeasure(String value) {
        if (value.equals("BB")) {
            throw new IllegalArgumentException("Invalid BB");
        }
        return value.length();
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "BB", "CCC", "DDDD");

        AtomicInteger mapped = new AtomicInteger();
        long mappedCount = words.stream()
                .map(s -> { mapped.incrementAndGet(); return s.toLowerCase(Locale.ROOT); })
                .count();
        System.out.println("map+count=" + mappedCount + ", map calls=" + mapped.get());

        AtomicInteger peeked = new AtomicInteger();
        long peekCount = words.stream()
                .peek(s -> peeked.incrementAndGet())
                .count();
        System.out.println("peek+count=" + peekCount + ", peek calls=" + peeked.get());

        long unvalidated = words.stream()
                .map(StreamSideEffectOptimizationDemo::validateAndMeasure)
                .count();
        System.out.println("validation in map+count=" + unvalidated);

        AtomicInteger checked = new AtomicInteger();
        long longWords = words.stream()
                .filter(s -> {
                    checked.incrementAndGet();
                    return s.length() > 2;
                }).count();
        System.out.println("filter+count=" + longWords + ", predicate calls=" + checked.get());

        AtomicInteger evaluated = new AtomicInteger();
        List<String> lower = words.stream()
                .map(s -> {
                    evaluated.incrementAndGet();
                    return s.toLowerCase(Locale.ROOT);
                }).toList();
        System.out.println("map+toList=" + lower + ", map calls=" + evaluated.get());

        AtomicInteger inspected = new AtomicInteger();
        boolean any = words.stream()
                .anyMatch(s -> {
                    inspected.incrementAndGet();
                    return s.equals("A");
                });
        System.out.println("anyMatch=" + any + ", predicate calls=" + inspected.get());

        StringBuilder actions = new StringBuilder();
        words.stream().map(s -> s.toLowerCase(Locale.ROOT))
                .forEachOrdered(s -> {
                    if (actions.length() > 0) actions.append("|");
                    actions.append(s);
                });
        System.out.println("forEachOrdered actions=" + actions);

        AtomicInteger slicedPeeked = new AtomicInteger();
        long sliceCount = words.stream().skip(1).limit(2)
                .peek(s -> slicedPeeked.incrementAndGet()).count();
        System.out.println("slice+count=" + sliceCount + ", peek calls=" + slicedPeeked.get());
    }
}
~~~

Chạy trên JDK 17 trở lên bằng:

~~~bash
javac --release 17 StreamSideEffectOptimizationDemo.java
java StreamSideEffectOptimizationDemo
~~~

**Stdout đã được kiểm chứng thực tế trong môi trường JDK dùng cho bài này:**

~~~text
map+count=4, map calls=0
peek+count=4, peek calls=0
validation in map+count=4
filter+count=2, predicate calls=4
map+toList=[a, bb, ccc, dddd], map calls=4
anyMatch=true, predicate calls=1
forEachOrdered actions=a|bb|ccc|dddd
slice+count=2, peek calls=0
~~~

### 9.1. Giải thích từng dòng

1. **`map+count=4, map calls=0`:** nguồn List có bốn phần tử; mapper giữ cardinality; count có thể được xác định mà không tạo bất kỳ chuỗi chữ thường nào.
2. **`peek+count=4, peek calls=0`:** callback chỉ quan sát, không ảnh hưởng số lượng; nó được phép không chạy khi count được suy ra từ nguồn.
3. **`validation in map+count=4`:** mapper `validateAndMeasure` sẽ ném exception cho `"BB"` **nếu được gọi**, nhưng ở phép đếm này nó bị bỏ qua và không có exception. Đây là minh chứng vì sao validation không nên dựa vào side effect của map.
4. **`filter+count=2, predicate calls=4`:** trong lần chạy này predicate xét cả bốn chuỗi để xác định hai chuỗi dài hơn hai ký tự.
5. **`map+toList=[a, bb, ccc, dddd], map calls=4`:** toList cần các giá trị đã chuyển đổi để dựng danh sách kết quả. Mapper thực sự được dùng trong pipeline này; bộ đếm ghi nhận bốn lần.
6. **`anyMatch=true, predicate calls=1`:** giá trị đầu tiên `"A"` đã đáp ứng điều kiện nên pipeline tuần tự kết thúc sớm. Những phần tử tiếp theo không cần kiểm tra.
7. **`forEachOrdered actions=a|bb|ccc|dddd`:** action của terminal operation được thực hiện cho các kết quả đã qua map theo thứ tự nguồn; ở đây dùng Stream tuần tự nên việc xây dựng StringBuilder không có ghi đồng thời.
8. **`slice+count=2, peek calls=0`:** skip một và limit hai trên List có kích thước đã biết; số phần tử kết quả có thể suy ra, không cần chạy peek.

**Không tuyệt đối hóa con số callback.** Đây là output thực nghiệm với JDK/nguồn/pipeline cụ thể; hợp đồng API bảo đảm **giá trị kết quả** và một số action terminal nhất định, không bảo đảm `map`/`peek` luôn bị bỏ qua hoặc chạy đúng số lần ghi nhận trong mọi môi trường.

## 10. Ba hướng thay thế đúng cho ba mục đích khác nhau

### 10.1. Mục tiêu A: biến đổi dữ liệu

Dùng một phép biến đổi **thuần dữ liệu**, để kết quả là phần được yêu cầu:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Nếu mục tiêu là danh sách chữ hoa, đây là API phù hợp. Không cần thêm bộ đếm ngoài, log hoặc action ghi file trong mapper. Giá trị của từng phần tử trong output được tạo theo ngữ nghĩa `map`.

### 10.2. Mục tiêu B: thống kê số lượng hoặc tổng

Dùng terminal operation diễn đạt kết quả:

~~~java
long longWordCount = words.stream()
        .filter(s -> s.length() >= 3)
        .count();

int totalLength = words.stream()
        .mapToInt(String::length)
        .sum();
~~~

Trong các biểu thức này, giá trị kết quả phụ thuộc vào predicate hoặc length. Nếu có cơ hội tối ưu hợp lệ, framework được quyền dùng. Không có yêu cầu side effect riêng nào phải “được thực hiện đủ n lần” để phép tính đúng.

### 10.3. Mục tiêu C: xử lý một hành động bắt buộc trên từng phần tử

Hãy làm lộ hành động trong workflow, ví dụ:

~~~java
for (String word : words) {
    System.out.println(word);
}
~~~

Hoặc:

~~~java
words.stream().forEachOrdered(System.out::println);
~~~

Cả hai đoạn minh họa là mã trong một phương thức, với `words` được khai báo trước. Nếu action có lỗi, phải xử lý theo hợp đồng đã thiết kế. Một terminal action không tự tạo bảo đảm exactly-once xuyên qua lỗi, retry, tiến trình chết hoặc thao tác với dịch vụ bên ngoài.

Nếu cần vừa **biến đổi** vừa **ghi ra bên ngoài**, thường tốt hơn khi tách hai giai đoạn: tạo dữ liệu đã chuẩn hóa/validate thành giá trị, sau đó xử lý ghi/commit với hợp đồng rõ. Đừng để một bước `map` vừa tạo giá trị vừa âm thầm cập nhật hệ thống khác mà những caller sau này có thể kết thúc bằng `count()`.

## 11. Cách kiểm thử để không mắc bẫy side effects

Một bộ test đáng tin cần kiểm tra **contract đầu ra**, không phải số lần logger xuất hiện trong pipeline.

### 11.1. Test kết quả của transformation

~~~java
List<String> actual = List.of("An", "Binh").stream()
        .map(String::toUpperCase)
        .toList();

// Kỳ vọng: ["AN", "BINH"]
~~~

Trong một dự án có JUnit, kiểm tra `assertEquals(List.of("AN","BINH"), actual)`. Không dùng `AtomicInteger` bên ngoài mapper làm bằng chứng transform chạy đủ hai lần nếu giá trị output mới là điều cần xác minh.

### 11.2. Test validation dưới dạng kết quả

Nếu validation cần trả lỗi cho từng phần tử, hãy kiểm tra `List<Result>` hoặc danh sách lỗi cụ thể. Ví dụ:
- Chuỗi hợp lệ tạo `Success` hoặc `Check(valid=true)`.
- Chuỗi sai tạo `Failure` có mã lỗi/vị trí.
- Danh sách kết quả giữ đúng vị trí, không âm thầm loại bỏ lỗi.
- Chỉ commit khi chính sách nghiệp vụ cho phép.

Không test rằng `map(validator).count()` ném exception, vì điều đó **không phải hợp đồng đáng tin**.

### 11.3. Test hành động bên ngoài tại ranh giới rõ

Nếu cần xác nhận đã gọi phương thức lưu, hãy đặt action trong service/hàm chịu trách nhiệm ghi và kiểm thử số lần gọi theo contract **của service ấy**, cùng kết quả khi lỗi và retry. Có thể dùng mock phù hợp với API đang kiểm thử, nhưng không dựa trên một intermediate side effect có thể bị JDK elide.

Đặc biệt nên có test:
- Nguồn rỗng.
- Một phần tử hợp lệ.
- Một phần tử không hợp lệ ở vị trí đầu, giữa, cuối.
- Nguồn lớn và những trường hợp chạy song song nếu hệ thống thật có dùng.
- Lỗi của hệ thống ghi sau khi một số phần tử đã được xử lý.

### 11.4. Không dựa vào hành vi của một JDK duy nhất

Kết quả thí nghiệm cho biết **JDK đã làm gì ở lần chạy này**. Nó không bắt buộc:
- Một JDK khác phải luôn tối ưu cùng cách.
- Những terminal operation khác phải giữ nguyên số callback.
- Có parallel thì tất cả lambda bắt buộc chạy nhiều thread.
- Việc thêm/bớt một operation không làm thay đổi khả năng tối ưu.

Thiết kế tốt có thể thay đổi cách tối ưu mà vẫn trả **đúng kết quả nghiệp vụ**.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sửa lại theo hợp đồng Stream |
| --- | --- |
| “Viết `peek` là đảm bảo log.” | `peek` không phải một audit/action guarantee; có thể không chạy |
| “Dùng `map` rồi `count` là vừa xử lý vừa đếm.” | Count có thể suy ra cardinality mà không gọi mapper |
| “Bật `parallel()` sẽ chạy mọi lambda.” | Parallel không làm mất quyền tối ưu bỏ operation |
| “Có AtomicInteger nên callback luôn được gọi.” | Atomic chỉ hỗ trợ đồng bộ hóa khi callback chạy, không ép invocation |
| “Không thấy exception tức là mọi phần tử hợp lệ.” | Validation đặt trong bước bị elide có thể chưa chạy |
| “`toList()` và `count()` luôn duyệt giống nhau.” | Mục tiêu khác nhau; `toList` cần giá trị đầu ra còn count chỉ cần số lượng |
| “Thêm `limit(2)` sẽ khiến peek chạy hai lần.” | Cardinality sau limit có thể tính mà không duyệt |
| “`findFirst()` đã chạy hết map cho mọi phần tử.” | Có thể short-circuit trước nhiều phần tử |
| “Stream tuần tự luôn buộc chạy mọi intermediate callback.” | Tuần tự không đồng nghĩa không tối ưu/elide |
| “Exception tự rollback side effects.” | Stream không cung cấp transaction/rollback |
| “forEach trên parallel luôn đúng thứ tự nguồn.” | Chỉ `forEachOrdered` có contract encounter order khi nguồn có thứ tự |
| “Record chứa List/Map là bất biến sâu.” | Trường tham chiếu vẫn có thể trỏ container mutable |
| “Đếm số dòng log là đếm phần tử xử lý.” | Log có thể bị bỏ, dừng sớm hoặc đảo thứ tự |
| “Callback đã chạy đủ trong một lần benchmark là hợp đồng JDK.” | Phải dựa vào API specification và kiểm chứng giá trị đầu ra |

Dòng có `toList()` trong bảng nhấn mạnh sự khác biệt **mục tiêu kết quả**, không tuyên bố mọi mapper trong mọi dạng toList phải có tác dụng phụ theo một lịch cố định.

## 13. Checklist thiết kế pipeline không phụ thuộc side effects

Trước khi đưa một lambda vào Stream, hãy tự hỏi:

1. **Mục tiêu cuối là một giá trị hay một hành động?** Nếu chỉ cần giá trị, tránh side effect.
2. **Callback có cần được gọi để tạo kết quả không?** Nếu không, JDK có thể bỏ qua nó.
3. **Đang dùng `peek` để thực hiện hành động bắt buộc?** Nếu có, phải thiết kế lại.
4. **Đang dùng `map(...).count()` để validate/lưu?** Nếu có, count không đủ làm bằng chứng.
5. **Kết quả của phép kiểm tra có được biểu diễn bằng giá trị không?** Nếu cần validation đầy đủ, trả Result/Failure rõ ràng.
6. **Terminal operation có thể dừng sớm không?** `anyMatch`, `findFirst`, `limit` không yêu cầu xử lý toàn bộ nguồn.
7. **Nguồn có kích thước biết trước không?** Nếu có, count càng có cơ hội tối ưu.
8. **Có yêu cầu thứ tự output/side effect?** Chọn đúng operation và kiểu nguồn ordered.
9. **Có xử lý song song không?** Kiểm soát thread safety, visibility, stateless/non-interfering.
10. **Có ghi file/database/API ngoài không?** Đảm bảo chính sách lỗi, timeout, idempotency và transaction ở boundary.
11. **Có đang tái sử dụng cùng Stream?** Stream không được dùng lại sau terminal operation.
12. **Đã test kết quả và trường hợp nguồn rỗng chưa?** Không chỉ đếm số dòng println.
13. **Đã đọc API Note và hợp đồng Java version mục tiêu chưa?** Không dựa vào trực giác về vòng lặp tuần tự.
14. **Nếu đổi terminal operation, code có còn đúng nghiệp vụ không?** Một design dựa trên side effect có thể hỏng ngay khi đổi `toList()` thành `count()`.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `List.of("a","b").stream().peek(System.out::println).count()` có thể không in phần tử nào?

**Đáp án:** List biết kích thước là hai, còn peek không đổi số phần tử. JDK có thể trả count trực tiếp mà không duyệt và không gọi action của peek.

**Câu 2.** Viết `map(validateOrThrow).count()` có bảo đảm kiểm tra mọi phần tử không?

**Đáp án:** Không. Map giữ cardinality nên có thể bị bỏ qua khi count được suy từ nguồn, dẫn đến cả validation và exception không xảy ra.

**Câu 3.** `filter(isValid).count()` trả điều gì?

**Đáp án:** Số phần tử hợp lệ theo predicate trong kết quả Stream. Với nguồn thông thường, muốn biết count phải xét điều kiện, nhưng không coi số lần gọi predicate là một hợp đồng side-effect độc lập.

**Câu 4.** `anyMatch(x -> x > 0)` trên danh sách bắt đầu bằng số dương có bắt buộc duyệt hết không?

**Đáp án:** Không. Chỉ cần tìm thấy một phần tử thỏa là có thể trả true.

**Câu 5.** `toList()` và `count()` có thể có khác biệt gì khi trước đó là `map(String::toLowerCase)`?

**Đáp án:** toList cần các chuỗi đã biến đổi để dựng output, còn count chỉ cần số phần tử, nên mapper có thể không cần chạy với count trên nguồn biết kích thước.

**Câu 6.** Nếu action lưu dữ liệu là bắt buộc, đặt trong `peek` có phù hợp không?

**Đáp án:** Không. Hãy sử dụng workflow hoặc terminal action có contract hành động rõ ràng, đồng thời thiết kế xử lý lỗi/commit/retry ở tầng ứng dụng.

**Câu 7.** AtomicInteger trong lambda giúp giải quyết vấn đề nào và không giải quyết vấn đề nào?

**Đáp án:** Nó hỗ trợ cập nhật bộ đếm một cách atomic khi có nhiều thread; nó **không** buộc JDK phải gọi lambda hoặc bảo đảm số lần gọi.

**Câu 8.** Vì sao `parallelStream().forEach(System.out::println)` không thể dùng để cam kết in theo thứ tự nguồn?

**Đáp án:** forEach với parallel không bảo đảm thứ tự action; nếu nguồn có encounter order và cần thực thi action theo thứ tự đó thì xem xét forEachOrdered hoặc vòng lặp tuần tự.

**Câu 9.** Một terminal operation ném exception có tự xóa những gì side effect đã ghi trước đó không?

**Đáp án:** Không. Cần transaction hoặc compensation thích hợp; Stream không là hệ quản trị giao dịch.

**Câu 10.** Khi nào nên dùng `peek`?

**Đáp án:** Chủ yếu để debug hoặc quan sát không thiết yếu khi phần tử thực sự được xử lý. Không dùng làm bước validation/audit/ghi dữ liệu bắt buộc.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 — Stream<T> và quyền tối ưu/elide intermediate operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Stream.count() API Note](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).
- [Java SE 17 — java.util.stream package summary: side effects, laziness và non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Java SE 17 — Stream.peek()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)).
- [Java SE 17 — Stream.forEachOrdered()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).
- [Java SE 17 — Spliterator và đặc tính SIZED](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

**Ghi nhớ:** Java Stream là mô tả **kết quả cần tính**, không phải bản cam kết chạy tuần tự từng callback trung gian. JDK có quyền bỏ qua `map`/`peek` hoặc cả một đoạn pipeline nếu kết quả terminal operation vẫn đúng; `count()` trên List biết kích thước là ví dụ điển hình. Những thao tác short-circuit còn có thể dừng trước khi xét hết nguồn. Vì vậy **đừng giấu validation, lưu trữ, audit hoặc tác dụng phụ bắt buộc trong intermediate operations**. Hãy đưa chúng vào contract xử lý thích hợp, dùng giá trị dữ liệu cho phép tính, và thiết kế concurrency/transaction độc lập với những tối ưu nội bộ của JDK.
