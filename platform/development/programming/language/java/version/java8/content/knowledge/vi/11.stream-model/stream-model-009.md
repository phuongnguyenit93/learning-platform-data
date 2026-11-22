# Tác dụng phụ và giới hạn của khả năng quan sát pipeline trong Java Stream

## 1. Mục tiêu học tập

**Stream pipeline** trong Java mô tả *cần tính toán kết quả nào* từ một nguồn dữ liệu thay vì chỉ rõ một vòng lặp phải chạy theo thứ tự bước nào. Cách tiếp cận này đem lại khả năng thực thi lazy, xử lý từng phần tử khi cần, tối ưu hóa và chạy song song. Nhưng cũng tạo ra một điểm khác biệt rất quan trọng với vòng lặp thông thường: **không được suy đoán hành vi bên trong pipeline bằng việc nhìn số lần một lambda có tác dụng phụ được gọi**.

Trong bài này, *tác dụng phụ* (*side effect*) nghĩa là hành vi làm thay đổi hoặc quan sát trạng thái ngoài kết quả trả về của phép biến đổi, chẳng hạn:

- Ghi log, in console, tăng bộ đếm.
- Ghi dữ liệu vào `List`, `Map`, cơ sở dữ liệu hoặc file.
- Gọi một HTTP API bên ngoài.
- Thay đổi một đối tượng mutable nằm trong nguồn Stream.
- Cập nhật shared state ở một thread khác.

*Khả năng quan sát pipeline* nghĩa là mức độ ta có thể tin vào các dấu vết như số lần gọi `map`, thứ tự các dòng in bởi `peek`, thread thực thi hay trạng thái bên ngoài để suy ra Stream đã làm những gì.

Bạn sẽ học cách:

1. Phân biệt nguồn Stream, intermediate operations và terminal operations.
2. Giải thích **lazy evaluation**, **short-circuiting** và khả năng **elide** (bỏ qua) các stage không cần thiết.
3. Hiểu tại sao `peek` thường hữu ích để debug nhưng **không phải audit hook, event callback hay bộ đếm tin cậy**.
4. Phân biệt *kết quả đầu ra được bảo đảm* với *thứ tự/số lần chạy các behavioral parameters không được bảo đảm*.
5. Tránh vi phạm nguyên tắc **non-interference**, **statelessness** và thread-safety, đặc biệt trong `parallelStream()`.
6. Thay side-effect accumulation bằng `collect`, `reduce`, `sum`, `count` hoặc cấu trúc điều khiển thích hợp.
7. Viết test và cơ chế ghi log/metrics dựa trên hợp đồng API thực sự, không phụ thuộc một chi tiết thực thi của JDK.

**Special Note — phạm vi hiện hành:** Tất cả cơ chế Stream nền tảng đều tiếp tục áp dụng trong Java hiện đại. Ví dụ chính biên dịch với Java 17+. Khi dùng API thêm sau Java 8, bài sẽ nêu rõ phiên bản.

## 2. Mô hình của một Stream pipeline

Một pipeline thông thường gồm:

~~~java
List<Integer> result = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();
~~~

Trong ví dụ:

| Thành phần | Biểu thức | Vai trò |
| --- | --- | --- |
| Source | `List.of(...).stream()` | Cung cấp các phần tử |
| Intermediate | `filter(...)` | Giữ phần tử thỏa điều kiện |
| Intermediate | `map(...)` | Chuyển đổi giá trị |
| Terminal | `toList()` | Tạo kết quả cuối |
| Kết quả | `[4, 16]` | Hợp đồng dữ liệu mà caller nhận |

`List.of` có từ Java 9; `Stream.toList()` có từ Java 16. Trên Java 8, một số chương trình tương đương có thể dùng `Arrays.asList(...)` và `collect(Collectors.toList())`, nhưng **các kiểu List trả về có hợp đồng khác nhau** nên không được coi chúng giống nhau về mutability.

Một Stream là một *description of computation*. Tạo Stream hay gắn `filter` và `map` **không mặc nhiên lặp qua toàn bộ nguồn ngay tại dòng khai báo**. Khi gọi terminal operation, pipeline mới được đánh giá theo nhu cầu của kết quả đó.

### Ví dụ về tính lazy

~~~java
AtomicInteger calls = new AtomicInteger();

Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> {
            calls.incrementAndGet(); // Chỉ để quan sát trong ví dụ.
            return n * n;
        });

System.out.println(calls.get()); // 0

List<Integer> result = pipeline.toList();
System.out.println(result);      // [1, 4, 9]
System.out.println(calls.get()); // 3 trong ví dụ cụ thể này
~~~

Mã cần import `AtomicInteger`, `Stream` và `List`, cũng xuất hiện trong chương trình hoàn chỉnh bên dưới. Vì kết quả `toList()` phải chứa các số bình phương, mapper của pipeline cụ thể này được dùng để tạo kết quả. Trước terminal operation, việc tạo intermediate stage chưa tính bình phương nào.

**Không suy rộng** từ việc `map` được gọi ba lần ở ví dụ này thành quy luật “mọi mapper của mọi pipeline chắc chắn chạy đúng một lần cho mỗi phần tử nguồn”. Một số terminal operations có thể suy kết quả mà không chạy một số intermediate operations.

## 3. Side effect khác kết quả Stream

Xét:

~~~java
List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();
~~~

`n -> n * 2` là phép biến đổi giá trị. Nó không thay đổi nguồn và không cập nhật trạng thái bên ngoài. Ta có thể reasoning về **giá trị đầu ra** theo hợp đồng Stream.

Ngược lại:

~~~java
AtomicInteger seen = new AtomicInteger();

long count = numbers.stream()
        .peek(n -> seen.incrementAndGet())
        .count();
~~~

Ta có hai việc độc lập:
- **Kết quả chính thức** của terminal operation: `count` là số phần tử.
- **Quan sát phụ**: `seen` đếm số lần `peek` thực sự được gọi.

Java Stream API cho phép tối ưu hóa mà **không thực thi một phần hoặc toàn bộ pipeline** khi vẫn giữ nguyên kết quả terminal. Vì vậy **không có bảo đảm chung** rằng `seen.get() == count`.

Một chương trình có thể trả `count == 4` nhưng `peek` không chạy lần nào nếu nguồn đã biết kích thước và pipeline không làm thay đổi số lượng phần tử. Đây là hành vi **được tài liệu Stream.count() cho phép**, không phải lỗi của Java.

### Mô hình tư duy đúng

**Sản phẩm phải đúng:** dữ liệu trả về, tổng, giá trị boolean, tập phần tử được chọn hoặc tác dụng rõ ràng của terminal operation theo đặc tả.

**Dấu vết trung gian không phải contract:** số lần chạy lambda, thread chạy lambda, thứ tự log của từng stage, hoặc những phần tử nào đã đi qua một `peek` trong quá trình đánh giá.

Đây là lý do không nên đặt cập nhật dữ liệu nghiệp vụ, gửi thông báo hay ghi audit quan trọng vào `peek` rồi giả định tất cả phần tử sẽ được xử lý đúng một lần.

## 4. Lazy evaluation và khả năng không có traversal

Đoạn:

~~~java
Stream<String> pipeline = Stream.of("A", "B", "C")
        .peek(System.out::println);
~~~

chỉ **tạo pipeline**. Vì chưa có terminal operation, thường sẽ không in `A`, `B`, `C` tại thời điểm này.

Khi thêm:

~~~java
pipeline.forEach(x -> {
    // Terminal action.
});
~~~

Stream bắt đầu được tiêu thụ. Nhưng điều này **không** có nghĩa mọi loại terminal operation đều cần thực thi các intermediate stages giống nhau.

### Ví dụ nổi bật: count() tối ưu hóa kích thước

~~~java
List<String> items = List.of("A", "B", "C", "D");

long total = items.stream()
        .peek(System.out::println)
        .count();

System.out.println("count=" + total);
~~~

`count` phải bằng `4`. Tuy nhiên, việc in bốn dòng từ `peek` **không được bảo đảm**. Đối với nguồn `List` có kích thước biết trước và stage `peek` không thay đổi số lượng phần tử, một Stream implementation có thể tính `count` trực tiếp từ size, không cần traversing, không chạy `peek`.

Trong các bản OpenJDK hiện đại, trường hợp này thường chỉ in:

~~~text
count=4
~~~

Đây là **đầu ra minh họa của một lựa chọn tối ưu hóa hợp lệ**, không phải cam kết mọi Java implementation bắt buộc cho output này. Nếu JDK khác thực hiện traversal, nó vẫn có thể hợp lệ miễn kết quả `count` đúng theo contract.

**Không “sửa” bằng cách chèn thêm một stage vô nghĩa** để ép `peek` chạy. Nếu một side effect thực sự bắt buộc, hãy đưa nó vào thiết kế xử lý rõ ràng, không phụ thuộc optimizer có bỏ qua stage không.

### Vì sao count có thể bỏ qua peek nhưng không được trả sai?

Stream API cho phép loại bỏ operations **nếu chứng minh được kết quả computation không thay đổi**. `peek` chỉ tác động bên ngoài; nó không biến phần tử thành nhiều hay ít phần tử. Với nguồn có số lượng xác định, terminal `count` chỉ cần con số này.

Ngược lại, với `filter` có predicate có thể loại phần tử, số lượng đầu ra nói chung **không thể tính trực tiếp chỉ từ kích thước nguồn**. Tuy nhiên, đừng tự dựng một quy tắc tổng quát rằng tất cả predicates luôn phải được gọi theo đúng số lượng; đặc tả vẫn cho phép tối ưu hóa hợp lệ trong bối cảnh cụ thể.

## 5. peek(): hữu ích để debug, không phải nơi gắn logic bắt buộc

`Stream.peek(Consumer)` là **intermediate operation**. Tài liệu chính thức mô tả công dụng chính là **hỗ trợ debug**, ví dụ xem phần tử ở một chặng pipeline:

~~~java
List<String> names = Stream.of("ann", "bob", "chris")
        .filter(s -> s.length() >= 4)
        .peek(s -> System.out.println("filtered: " + s))
        .map(String::toUpperCase)
        .peek(s -> System.out.println("mapped: " + s))
        .toList();
~~~

Đây là **mã minh họa** trong ngữ cảnh imports thích hợp. Nó giúp quan sát khi các callbacks được chạy, nhưng:

- Intermediate `peek` chỉ được gọi khi phần tử thực sự được xử lý qua stage đó.
- Short-circuit có thể làm một số phần tử không đến `peek`.
- Một optimizer có thể bỏ stage nếu kết quả chính không cần nó.
- Trong parallel pipeline, action có thể chạy ở những threads khác nhau, không theo thứ tự nguồn.
- Log được in ra **không nhất thiết phản ánh thứ tự hoàn tất hoặc thứ tự materialization của terminal result**.
- Nếu nguồn/terminal khác nhau, hành vi log cũng có thể khác.

### Không dùng peek cho nghiệp vụ quan trọng

~~~java
// Thiết kế rủi ro: ghi DB bên trong intermediate stage.
long count = orders.stream()
        .peek(order -> repository.save(order))
        .count();
~~~

Dù `orders` chứa nhiều phần tử, không được dựa vào việc `repository.save` luôn được gọi. Nếu số lượng phần tử đầu ra đã biết, optimizer có thể không traverse stage `peek`. Ngoài ra, khi chạy parallel, gọi database không đồng bộ, lặp lại retry hoặc thất bại giữa chừng cần hợp đồng riêng.

Nếu mục tiêu là **ghi mỗi order**, hãy dùng một quy trình xử lý rõ ràng với error handling, transaction và retry semantics tương ứng. Nếu pipeline chỉ cần **tính số order**, hãy giữ stream transformation thuần và để `count` làm việc của nó.

## 6. Short-circuiting: không phải phần tử nào cũng đi qua mọi stage

Một số terminal operations có thể **dừng khi đủ thông tin**:

- `findFirst()`: trả phần tử đầu phù hợp theo encounter order của một ordered stream.
- `findAny()`: có thể trả một phần tử bất kỳ; hữu ích cho parallel execution và không bảo đảm đó là phần tử đầu.
- `anyMatch(predicate)`: trả true khi có phần tử thỏa, có thể không kiểm tra phần còn lại.
- `allMatch(predicate)`: có thể dừng sớm khi gặp phần tử không thỏa.
- `noneMatch(predicate)`: có thể dừng sớm khi gặp phần tử thỏa.

Một số intermediate operations cũng giới hạn số phần tử cần cho downstream:

- `limit(n)`: chỉ lấy tối đa `n` phần tử.
- `takeWhile(predicate)`: lấy prefix thỏa điều kiện đối với ordered stream (Java 9+).
- `dropWhile(predicate)`: bỏ prefix đầu thỏa điều kiện đối với ordered stream (Java 9+).

Ví dụ:

~~~java
boolean hasOdd = Stream.of(2, 4, 5, 8)
        .anyMatch(n -> n % 2 != 0);
~~~

Kết quả là `true`. Pipeline **không cần thiết** kiểm tra phần tử `8` để biết có số lẻ. Nếu bạn đặt `peek(log)` ở trước `anyMatch`, đừng giả định mọi số đều được log.

### Không dựa vào “đã gọi đúng bao nhiêu lần”

Có thể bạn thấy một lần chạy sequential dừng ngay khi gặp `5` và predicate được gọi ba lần. Nhưng không nên biến **số lần gọi predicate** thành cơ chế kiểm tra nghiệp vụ, đặc biệt khi thay bằng parallel stream.

Với parallel execution, nhiều tasks có thể đã được lên lịch và xử lý phần tử khác trước khi một task đưa ra kết quả short-circuit. Số lượng phần tử thực sự đã đi qua từng callback có thể thay đổi theo lịch thực thi, kích thước nguồn và optimizer.

**Contract được hứa là kết quả boolean/Optional**, không phải “đúng ba callbacks đã chạy”.

## 7. Stateful intermediate operations và giới hạn quan sát

Một số intermediate operations cần thông tin của nhiều phần tử, ví dụ:

- `sorted()` sắp xếp.
- `distinct()` loại trùng.
- `limit()`, `skip()` giữ/bỏ một phần của chuỗi.
- `takeWhile()`, `dropWhile()` xử lý prefix tùy nguồn và encounter order.

Điều này ảnh hưởng **thứ tự và thời điểm** callbacks trước/sau stage có thể chạy. Ví dụ:

~~~java
List<Integer> result = Stream.of(5, 1, 4, 2)
        .sorted()
        .filter(n -> n % 2 == 0)
        .toList();

// result: [2, 4]
~~~

Kết quả đầu ra có thể khẳng định. Nhưng nếu cài `peek(System.out::println)` trước và sau `sorted`, việc suy ra một lịch chạy chính xác cho mọi stream implementation từ các dòng log là không an toàn.

Với ordered parallel pipeline, các stage như `limit` và `skip` có thể tốn chi phí hơn vì phải tôn trọng encounter order. `unordered()` có thể giảm ràng buộc khi nghiệp vụ **không yêu cầu thứ tự**, nhưng điều này thay đổi hợp đồng và không phù hợp nếu bạn cần “đúng n phần tử đầu”.

### Stream không phải vòng for ghép theo từng dòng mã

Một vòng `for` thường có thứ tự chương trình cụ thể cho mỗi iteration. Stream mô tả các transformations có thể được kết hợp, phân hoạch, short-circuit, hoặc tối ưu. Do đó không thể suy nghĩ “bước filter chạy cho tất cả phần tử, xong bước map chạy cho tất cả phần tử” như một quy tắc tổng quát. Điều phải giữ là **semantics kết quả** theo đặc tả.

## 8. Non-interference: không thay đổi nguồn trong pipeline

Các **behavioral parameters** (lambda, method reference, predicates, mappers) thông thường phải **non-interfering**: không sửa đổi nguồn Stream trong lúc pipeline đang được đánh giá, trừ những trường hợp nguồn được thiết kế cho concurrent modification và semantics của nó cho phép.

Ví dụ dễ sai:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

values.stream()
        .forEach(n -> values.add(n * 10)); // Không nên làm.
~~~

Code này **sửa nguồn `values` đang được traverse**. Hành vi có thể sai, ném `ConcurrentModificationException` hoặc cho kết quả khó dự đoán. Không dựa vào exception như một cơ chế phát hiện mọi lần vi phạm: fail-fast detection là **best effort**, không phải một bảo đảm đầy đủ.

Một số nguồn concurrent như `ConcurrentHashMap` được thiết kế cho truy cập/thay đổi đồng thời và có spliterator đặc trưng, nhưng điều đó **không** biến việc sửa collection tùy tiện thành an toàn cho mọi nguồn Stream.

### Cách đúng: tạo collection kết quả riêng

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

List<Integer> extended = values.stream()
        .map(n -> n * 10)
        .toList();

// values:   [1, 2, 3, 4]
// extended: [10, 20, 30, 40]
~~~

Thao tác ánh xạ tạo giá trị mới mà không sửa nguồn. Đây là thiết kế dễ reasoning, dễ test và có khả năng parallelize tốt hơn.

### Cẩn trọng với mutation của phần tử

Không sửa trực tiếp `List` không đồng nghĩa không có side effect. Ví dụ `map(user -> { user.setActive(true); return user; })` thay đổi **objects trong nguồn**, có thể gây tác động quan sát được từ nơi khác. Nếu nhiều threads chia sẻ các objects đó hoặc nếu callbacks phụ thuộc trạng thái mutable, pipeline có thể mất tính stateless.

Khi cần cập nhật trạng thái thực thể, hãy xác định rõ boundary của mutation và transaction. Đừng mặc nhiên chọn `map` chỉ vì có thể trả chính object vừa sửa.

## 9. Statelessness: đừng để kết quả phụ thuộc shared mutable state

Ví dụ có một bộ đếm dùng trong mapper:

~~~java
AtomicInteger nextId = new AtomicInteger();

List<String> labeled = source.parallelStream()
        .map(s -> nextId.incrementAndGet() + ":" + s)
        .toList();
~~~

`AtomicInteger` có thể bảo vệ việc tăng counter khỏi data race, nhưng **không bảo đảm element đầu tiên trong encounter order được ID 1, element thứ hai được ID 2**, vì các tasks có thể chạy bất kỳ thứ tự nào.

Điều này minh họa hai vấn đề khác nhau:

1. **Thread safety**: thao tác tăng có bị lost update không?
2. **Determinism của mapping**: giá trị ID gắn với từng element có ổn định theo encounter order không?

Atomic counter giúp vấn đề 1, nhưng **không giải quyết vấn đề 2**. Nếu ý nghĩa nghiệp vụ là chỉ số theo thứ tự, hãy tạo chỉ số bằng phương pháp bảo đảm đúng quan hệ index-to-element, ví dụ duyệt theo index trên một List hoặc xử lý tuần tự có chủ đích.

### Stateful predicates gây kết quả bất ổn

~~~java
Set<Integer> seen = Collections.synchronizedSet(new HashSet<>());

List<Integer> result = source.parallelStream()
        .filter(seen::add)
        .toList();
~~~

Dù Set được synchronized, **phần tử nào được xét trước** vẫn phụ thuộc scheduling. Với phần tử trùng có dữ liệu gắn kèm, logic chọn bản đại diện có thể không ổn định. Không nên xem việc khóa Set là đủ để biến một predicate có state thành một phép biến đổi phù hợp với stream contract.

Nếu mục tiêu là lấy các giá trị distinct, dùng `distinct()`; nếu cần chọn bản đại diện theo quy tắc nghiệp vụ rõ, sử dụng collector, grouping hoặc một cấu trúc thuật toán xác định.

## 10. Parallel streams: kết quả có thứ tự không có nghĩa callback chạy có thứ tự

Một stream có thể có **encounter order** bắt nguồn từ một `List`, mảng hoặc ordered range. Ví dụ:

~~~java
List<Integer> result = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * n)
        .boxed()
        .toList();
~~~

Kết quả theo encounter order:

~~~text
[1, 4, 9, 16, 25]
~~~

Nhưng **không có lời hứa** rằng mapper đã chạy theo thứ tự `1,2,3,4,5` hay chạy trên một thread. Nó có thể thực thi theo chunks trên nhiều worker threads, sau đó terminal operation tổ hợp kết quả theo thứ tự cần thiết.

Từ đó:

- Output `toList()` ổn định cho ordered source + transformations phù hợp.
- `peek(System.out::println)` trong một parallel stage có thể in không theo encounter order.
- `map(n -> { log(n); return ...; })` không bảo đảm logging order giống result order.
- Một phần tử có thể trải qua các callbacks/stages ở những threads khác nhau tùy cách implementation tổ chức pipeline.
- Việc một kết quả xuất hiện ở vị trí thứ ba **không chứng minh** callback tạo nó là callback thứ ba được chạy.

### Không có bảo đảm về visibility của side effects tùy ý

Tài liệu package `java.util.stream` nêu rõ, trừ khi được đặc tả riêng, không có bảo đảm chung về **visibility của side effects giữa threads**, thread nào xử lý các stages của cùng phần tử, hay liệu behavioral parameters có luôn được gọi không.

Nếu hai callbacks cùng đọc/ghi một biến mutable không có đồng bộ, chúng có thể tạo data race. Không nên dựa vào việc “kết quả in trên máy mình trông đúng” để kết luận thiết kế an toàn.

## 11. forEach và forEachOrdered: giống nhau ở đâu, khác nhau ở đâu?

`forEach(action)` và `forEachOrdered(action)` là **terminal operations** thực hiện actions để tạo side effects. Theo tài liệu Stream, đây là những trường hợp có cam kết riêng về việc thực thi actions, khác với một số intermediate operations có thể bị elide.

### forEach

~~~java
List.of("A", "B", "C")
        .parallelStream()
        .forEach(System.out::println);
~~~

Nó thực hiện action cho từng phần tử của stream được terminal xử lý, nhưng **không bảo đảm thứ tự action** với parallel stream. Các dòng có thể in không theo thứ tự A, B, C.

### forEachOrdered

~~~java
List.of("A", "B", "C")
        .parallelStream()
        .forEachOrdered(System.out::println);
~~~

Với ordered source như `List`, `forEachOrdered` thực hiện terminal action **theo encounter order**. Vì thế ta kỳ vọng chuỗi ba dòng:

~~~text
A
B
C
~~~

Tuy nhiên, **không suy ra** toàn bộ upstream pipeline chạy lần lượt A rồi B rồi C. `forEachOrdered` bảo đảm thứ tự **terminal action**, không đặt một quy tắc global về thread/scheduling của mọi `map`/`filter`/`peek` phía trước.

Theo Javadoc, action thực hiện trên một phần tử **happens-before** action của phần tử tiếp theo trong encounter order; nhưng action trên các phần tử khác nhau vẫn có thể được thực thi bởi threads khác nhau. Nếu cần tính toán song song rồi cập nhật tài nguyên ngoài có ordering, hãy cân nhắc hiệu năng và hợp đồng external system thay vì cho rằng `forEachOrdered` tự giải quyết transaction/retry.

### Không có exactly-once delivery guarantee cho hệ thống bên ngoài

Một terminal `forEach` đang ghi DB có thể thất bại ở phần tử giữa chừng. Stream API không cung cấp transaction phân tán, retry semantics hay exactly-once delivery khi process bị dừng hoặc side effects một phần đã xảy ra.

Nếu việc ghi dữ liệu là nghiệp vụ quan trọng, bạn cần transaction boundaries, idempotency keys, error handling và cơ chế retry theo thiết kế ứng dụng. Đừng suy từ “terminal action sẽ được gọi” thành “mọi side effect đã commit chính xác một lần trong mọi tình huống”.

## 12. Thu thập dữ liệu bằng collect/toList thay vì side-effect forEach

Một anti-pattern phổ biến:

~~~java
List<Integer> output = new ArrayList<>();

source.parallelStream()
        .filter(n -> n % 2 == 0)
        .forEach(output::add);
~~~

`ArrayList` không an toàn để nhiều tasks thêm phần tử đồng thời. Có thể gặp lost updates, sai dữ liệu hoặc exception, và thứ tự thêm cũng không được bảo đảm bởi `forEach`.

### Cách dùng stream phù hợp

~~~java
List<Integer> output = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Terminal `toList()` sẽ tự điều phối việc tạo kết quả theo hợp đồng Stream. Với ordered source và những operations bảo toàn encounter order, thứ tự phần tử trong kết quả phù hợp encounter order.

**Không đánh đồng mutability:**
- `Stream.toList()` (Java 16+) trả về **unmodifiable List**. Không thể gọi `add` vào kết quả.
- `collect(Collectors.toList())` tạo List nhưng đặc tả **không bảo đảm loại implementation, mutability, serializability hay thread-safety**.
- Nếu thực sự cần một `ArrayList` có thể sửa, dùng `collect(Collectors.toCollection(ArrayList::new))`.

Ví dụ:

~~~java
ArrayList<Integer> modifiable = source.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toCollection(ArrayList::new));

modifiable.add(100);
~~~

Chương trình trên là mã minh họa, giả định `source` là collection số nguyên. Collection được tạo và tích lũy **qua collector** thay vì để nhiều lambda bên ngoài cùng mutate một List.

## 13. reduce, sum, count và grouping: đầu ra là hợp đồng

Khi cần tính tổng, đừng tạo một biến mutable chung rồi cập nhật trong `map` hoặc `peek`:

~~~java
// Thiết kế rủi ro nếu chạy song song.
int[] total = {0};
numbers.parallelStream()
        .forEach(n -> total[0] += n);
~~~

Tăng `total[0]` từ nhiều threads mà không đồng bộ gây data race.

Cách đúng:

~~~java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Hoặc, với các giá trị phù hợp:

~~~java
int total = numbers.stream()
        .reduce(0, Integer::sum);
~~~

`reduce` cần một phép kết hợp **associative** và identity phù hợp để hoạt động tốt với parallel execution. Phép trừ hoặc phép toán phụ thuộc thứ tự thường không thích hợp làm accumulator cho reduction song song nếu không thỏa contract.

Một ví dụ grouping không dùng side effects từ client:

~~~java
Map<Boolean, List<Integer>> groups = numbers.stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));
~~~

Không cần tự tạo `HashMap` rồi cập nhật trong `peek`. Terminal `collect` cung cấp cơ chế accumulation/combining phù hợp, nhưng vẫn phải dùng collector đúng contract.

**Đừng khẳng định Map từ grouping/partitioning luôn có iteration order mong muốn** nếu API không hứa điều đó. Nếu output cần thứ tự trình bày nhất định, sắp xếp/truy vấn theo key hoặc chọn collector/map phù hợp.

## 14. Stream nhiều lần duyệt: quan sát và reuse sai

Một Stream thường là **single-use abstraction**. Sau khi một terminal operation tiêu thụ stream, không được dùng lại pipeline đó cho terminal khác:

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3);
long count = stream.count();

// Sai: cùng stream đã được consume.
// List<Integer> values = stream.toList();
~~~

Java Stream API có thể phát hiện reuse và ném `IllegalStateException`; không nên viết code dựa vào reuse dù một implementation ở trường hợp đặc biệt không phát hiện được.

Nếu cần hai kết quả:
- Tạo **hai Stream mới** từ một nguồn có thể duyệt lại an toàn.
- Hoặc dùng một collector/summaryStatistics tùy mục đích.
- Hoặc materialize dữ liệu một lần thành collection rồi tính tiếp.

Nhưng đừng dựa vào `peek` của lần duyệt đầu để làm nguồn dữ liệu cho lần duyệt sau.

### Thói quen debug nguy hiểm

~~~java
Stream<Order> s = orders.stream();
System.out.println(s.count());
s.forEach(this::processOrder); // Không hợp lệ: stream reuse.
~~~

Cách sửa **không** phải cố reset Stream; dùng `orders.stream()` mới mỗi lần nếu nguồn có thể duyệt lại, hoặc xử lý trong một pass nếu dữ liệu tốn kém/không thể đọc lại. Đây là giới hạn Stream hiện đại, không phải lỗi thời của Java 8.

## 15. Side effects và xử lý resource ngoài Stream

Một Stream có thể được tạo từ file hoặc channel:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Đây là **đoạn minh họa** với `path` có kiểu `Path` và nơi gọi xử lý `IOException`. `Files.lines` có từ Java 8; `String.isBlank()` có từ Java 11. Stream đọc file có thể cần đóng tài nguyên I/O.

Điểm quan trọng:

- Stream source được đọc **lazy** khi terminal operation cần dữ liệu.
- `Files.lines(...)` trả stream có tài nguyên cần được đóng khi dùng xong; dùng `try-with-resources`.
- Terminal operation như `count()` **không tự thay thế** hành động `close()` bắt buộc theo resource contract.
- `onClose(action)` đăng ký handler **khi Stream được close**, không phải một callback “bảo đảm chạy sau mọi terminal operation” ngay cả khi caller quên close.
- Nếu pipeline short-circuit, phần dữ liệu thực sự đọc có thể ít hơn toàn bộ file; cần đóng resource kể cả vậy.

Không dùng `peek` như một cơ chế tự đóng file hoặc giải phóng transaction. Tài nguyên cần lifetime management tường minh và exception-safe.

## 16. Điều gì thực sự quan sát được trong production?

### A. Kết quả được tiêu thụ

Bạn có thể log/kiểm thử **sau terminal operation**:

~~~java
List<String> output = input.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .toList();

logger.info("Created {} elements", output.size());
~~~

Đây là **mã minh họa** với logger, input và import được cung cấp bởi dự án. Nó đo **kích thước kết quả đã materialize**, thay vì đếm số lần `peek` được gọi. `String.strip` có từ Java 11.

### B. Chi phí vận hành

Nếu cần đo thời gian truy vấn/pipeline, đo xung quanh **terminal operation**, không đo chỉ lúc tạo intermediate stream:

~~~java
long start = System.nanoTime();

List<Integer> output = input.stream()
        .map(this::convert)
        .toList();

long elapsedNanos = System.nanoTime() - start;
~~~

Đây là mã minh họa trong class có `input` và `convert` phù hợp. `System.nanoTime()` phục vụ đo khoảng thời gian, không phải timestamp wall-clock. Chỉ đếm thời gian tạo `input.stream().map(...)` sẽ không đo phần lớn công việc thực hiện bởi terminal operation.

### C. Đếm operations cụ thể

Nếu mục đích là biết chính xác bao nhiêu **bản ghi đầu ra** được tạo thành công, đếm từ output đã được tạo hoặc dùng một terminal operation phù hợp. Nếu mục đích là đo mỗi **yêu cầu I/O** gửi ra ngoài, instrument tại **API thật sự gửi yêu cầu** với metrics có semantics rõ, không dùng `peek` để suy ngược.

### D. Audit và transaction

Nếu audit log phải ghi sau khi dữ liệu được commit, đặt instrumentation tại transaction boundary hoặc cơ chế audit được framework hỗ trợ. Việc `map` hoặc `forEach` gọi code không chứng minh transaction đã commit, đặc biệt nếu một exception xuất hiện ở phần tử sau.

## 17. Chương trình Java 17+ hoàn chỉnh có stdout xác định

Chương trình này minh họa tính lazy, kết quả của các transformations thuần, short-circuit ở mức **kết quả logic**, parallel result giữ encounter order và cách dùng `AtomicInteger` an toàn trong **terminal `forEach`**. Đoạn dùng side effect để minh họa chỉ dùng trong ví dụ giảng dạy, không khuyến nghị lấy counter này làm logic nghiệp vụ.

Lưu tệp tên **`StreamSideEffectsDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamSideEffectsDemo {
    public static void main(String[] args) {
        AtomicInteger mapped = new AtomicInteger();

        Stream<Integer> prepared = Stream.of(1, 2, 3)
            .map(n -> {
                mapped.incrementAndGet();
                return n * n;
            });

        System.out.println("before-terminal=" + mapped.get());

        List<Integer> squares = prepared.toList();
        System.out.println("squares=" + squares);
        System.out.println("mapped=" + mapped.get());

        List<Integer> evens = IntStream.rangeClosed(1, 8)
            .filter(n -> n % 2 == 0)
            .boxed()
            .toList();
        System.out.println("evens=" + evens);

        boolean anyDog = Stream.of("cat", "dog", "owl")
            .anyMatch(s -> s.startsWith("d"));
        System.out.println("anyDog=" + anyDog);

        String joined = Stream.of("java", "stream", "api")
            .map(s -> s.toUpperCase(Locale.ROOT))
            .collect(Collectors.joining("/"));
        System.out.println("joined=" + joined);

        List<Integer> parallelSquares = IntStream.rangeClosed(1, 5)
            .parallel()
            .map(n -> n * n)
            .boxed()
            .toList();
        System.out.println("parallel-squares=" + parallelSquares);

        int sum = IntStream.rangeClosed(1, 5).parallel().sum();
        System.out.println("sum=" + sum);

        AtomicInteger seen = new AtomicInteger();
        IntStream.range(0, 6).parallel()
            .forEach(n -> seen.incrementAndGet());
        System.out.println("forEach-count=" + seen.get());
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc JDK mới hơn hỗ trợ mục tiêu `--release 17`:

~~~bash
javac --release 17 StreamSideEffectsDemo.java
java StreamSideEffectsDemo
~~~

**Stdout xác định đã kiểm tra bằng cách biên dịch và chạy Java 17-compatible code:**

~~~text
before-terminal=0
squares=[1, 4, 9]
mapped=3
evens=[2, 4, 6, 8]
anyDog=true
joined=JAVA/STREAM/API
parallel-squares=[1, 4, 9, 16, 25]
sum=15
forEach-count=6
~~~

### Diễn giải từng kết quả

1. `before-terminal=0`: `prepared` mới chỉ là mô tả; mapper chưa được yêu cầu chạy.
2. `squares=[1, 4, 9]`: terminal `toList` cần những giá trị bình phương.
3. `mapped=3`: ở pipeline cụ thể này, mapper tạo đúng ba giá trị cần thiết; đây **không** phải định luật về số lần gọi mọi mapper ở mọi pipeline.
4. `evens=[2, 4, 6, 8]`: `filter` quyết định output; result là điều cần test.
5. `anyDog=true`: tồn tại chuỗi bắt đầu bằng `d`; output boolean không tiết lộ đầy đủ predicate đã chạy bao nhiêu lần.
6. `joined=JAVA/STREAM/API`: các phép ánh xạ chuỗi và joining tạo dữ liệu xác định theo encounter order.
7. `parallel-squares=[1, 4, 9, 16, 25]`: ordered source có ordered result; **không khẳng định** thứ tự các threads chạy `map`.
8. `sum=15`: terminal reduction tổng hợp kết quả, không cần biến mutable bên ngoài.
9. `forEach-count=6`: terminal action `forEach` thực hiện trên sáu phần tử của `IntStream.range(0,6)`; `AtomicInteger` ngăn lost updates. **Không** đồng nghĩa `peek` ở một intermediate stage luôn được gọi sáu lần.

Chương trình không in `Thread.currentThread().getName()` hoặc log từ parallel `map` vì thứ tự và tên threads không phải đầu ra xác định theo hợp đồng Java Stream. Nếu muốn quan sát chúng trong môi trường thử nghiệm, có thể thêm log riêng nhưng không dùng output ấy làm đáp án cố định.

## 18. Ví dụ quan sát tối ưu hóa count() — output phụ thuộc implementation

Đoạn sau được tách khỏi chương trình có stdout cố định:

~~~java
AtomicInteger peekCalls = new AtomicInteger();

long n = List.of(10, 20, 30, 40).stream()
        .peek(x -> peekCalls.incrementAndGet())
        .count();

System.out.println("count=" + n);
System.out.println("peekCalls=" + peekCalls.get());
~~~

Khi dùng nguồn `List` đã biết kích thước và không có stage đổi số lượng phần tử, một Stream implementation **được phép** không thực hiện `peek`. Một JDK có thể in:

~~~text
count=4
peekCalls=0
~~~

Nhưng **`peekCalls=0` không phải output bắt buộc của mọi implementation**. Đây là điểm mấu chốt của bài: nếu code cần `peekCalls` để quyết định xử lý tiếp, thiết kế ấy đã dựa vào một thuộc tính **không được contract bảo đảm**.

Điều chắc chắn là `count=4`, miễn dữ liệu nguồn trong ví dụ ổn định và không vi phạm quy tắc sử dụng Stream. Những kết luận về side effects phải theo Javadoc, không theo một lần chạy tình cờ.

## 19. Bộ lỗi phổ biến và cách sửa

| Vấn đề | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| Dùng `peek` để lưu DB | Stage có thể bị bỏ qua hoặc không xử lý mọi phần tử | Phương thức xử lý nghiệp vụ/transaction rõ ràng |
| Dùng `peek` để đo số event “đã xử lý” | `count` và short-circuit có thể không chạy `peek` | Đo tại boundary xử lý thật hoặc từ terminal result |
| `forEach(list::add)` trên parallel stream | List mutable thường không thread-safe | `collect`/`toList` |
| Dùng `AtomicInteger` làm index trong parallel `map` | Counter thread-safe nhưng thứ tự gán index bất định | Indexing có hợp đồng thứ tự hoặc xử lý tuần tự |
| Sửa nguồn trong `filter`/`forEach` khi đang traverse | Vi phạm non-interference | Tạo kết quả mới rồi cập nhật theo boundary riêng |
| Kỳ vọng log trong `map` đúng encounter order | Mapper có thể chạy trên threads bất kỳ | Log output sau terminal hoặc dùng terminal `forEachOrdered` cho thứ tự action |
| Kỳ vọng `forEachOrdered` tuần tự hóa toàn bộ upstream | Chỉ bảo đảm thứ tự terminal action | Không dùng upstream side effects để suy thứ tự |
| Kỳ vọng `anyMatch` kiểm tra tất cả phần tử | Short-circuit terminal | `forEach`/vòng lặp nếu cần xử lý thật mọi item, có error semantics rõ |
| Kỳ vọng `count()` chạy toàn bộ `peek` | Có thể suy size trực tiếp | Không dùng intermediate side effects |
| Dùng `reduce` với accumulator không associative | Parallel combination có thể đổi kết quả | Phép reduction associative và identity hợp lệ |
| Dùng lại Stream sau terminal | Stream single-use | Tạo Stream mới hoặc materialize collection |
| Quên close `Files.lines` | Stream có resource I/O | `try-with-resources` |
| Dùng `onClose` như “after terminal callback” | Chạy khi close, không tự động ngay sau terminal | Gọi close trong scope phù hợp hoặc xử lý sau terminal tường minh |
| So sánh chính xác thứ tự `peek` trong test | Thứ tự/callback count không phải API contract | Assert dữ liệu cuối và hợp đồng ordering thực sự |
| Cho rằng `parallel()` luôn nhanh hơn | Phân hoạch/đồng bộ/ordering có chi phí | Benchmark thực tế trên workload phù hợp |

## 20. Khi nào nên dùng vòng lặp thay cho Stream?

Stream phù hợp khi mục tiêu chính là **chuyển đổi, lọc, tổng hợp dữ liệu** theo cách declarative. Nhưng vòng lặp hoặc một service xử lý tường minh thường rõ hơn nếu yêu cầu chính là:

- Gửi một request cho từng phần tử và cần kiểm soát lỗi theo item.
- Ghi mỗi record vào database với transaction/retry/idempotency chính xác.
- Ghi audit theo thứ tự bắt buộc, phải biết request đã commit hay chưa.
- Cập nhật tài nguyên mutable chung phải bảo đảm đồng bộ.
- Cần dừng, rollback hoặc tiếp tục theo một chính sách exception chi tiết.
- Mỗi lần xử lý phải tạo một side effect bên ngoài và **đó chính là mục tiêu**, không phải “dấu vết” của phép tính.

Ví dụ vòng lặp minh bạch:

~~~java
for (Order order : orders) {
    processOrder(order); // Mỗi lượt xử lý được điều phối tường minh.
}
~~~

Đây là mã minh họa có `orders` và `processOrder` của ứng dụng. Nó không tự giải quyết failure/retry/transaction, nhưng ít nhất side effects là **mục đích trực tiếp của cấu trúc điều khiển**, không bị giấu trong intermediate stage mà Stream optimizer được phép loại bỏ.

Nếu việc xử lý rất lớn và cần song song, cân nhắc một mô hình concurrency với queue, executor, structured concurrency tương ứng baseline, hoặc batch processing framework có semantics rõ, thay vì mặc định `parallelStream().peek(repository::save)` là giải pháp đúng.

## 21. Thiết kế kiểm thử đúng contract

Với một pipeline:

~~~java
List<Integer> output = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10)
        .toList();
~~~

Unit test nên assert:

~~~java
if (!output.equals(List.of(10, 30, 50))) {
    throw new AssertionError("Unexpected stream result");
}
~~~

Không assert “filter đã được gọi đúng năm lần và map đúng ba lần” trừ khi ứng dụng tự đặt và bảo đảm một hợp đồng độc lập ở tầng cụ thể khác. Những invocation counts không phải sản phẩm chính của Stream pipeline và có thể nhạy cảm với implementation/short-circuit.

### Kiểm thử parallel

Khi chạy pipeline ở dạng parallel, kiểm tra:
- Kết quả phần tử/tổng đúng.
- Có hay không yêu cầu encounter order và terminal operation có giữ order theo contract không.
- Mapper/predicate không phụ thuộc mutable shared state.
- Không có mutation nguồn trong khi traversal.
- Nếu có side effects bên ngoài, chúng đã được quản lý bằng cơ chế thích hợp, không dựa vào timing của các stages.

### Benchmark

Không benchmark chỉ bằng số lượng log hoặc thời gian khai báo `stream().map(...)`. Chạy workload qua terminal operation và đánh giá data size, allocation, contention, cost của `sorted`/`distinct`, ordered vs unordered semantics. Khi cần benchmark nghiêm túc, dùng phương pháp đo JIT warmup và công cụ như JMH được duy trì, thay vì suy luận từ một lần `System.nanoTime`.

## 22. Bài tập thực hành

**Bài 1 — Lười thực thi.** Tạo `Stream.of(1,2,3).map(...)` có bộ đếm `AtomicInteger` nhưng không có terminal. Dự đoán bộ đếm và giải thích vì sao.

**Bài 2 — count và peek.** Với `List.of("A","B","C").stream().peek(System.out::println).count()`, vì sao không được cam kết ba dòng `peek` sẽ xuất hiện? Kết quả `count` phải là gì?

**Bài 3 — Short-circuit.** Cho `anyMatch` tìm số âm trong `Stream.of(5,3,-1,8)`. Điều gì là contract của kết quả? Vì sao không nên assert chính xác số lần predicate được gọi trong mọi pipeline?

**Bài 4 — Parallel map order.** Một ordered source được xử lý bằng `parallel().map(x -> x*2).toList()`. Hãy giải thích vì sao result có thứ tự nhưng log trong mapper có thể xuất hiện theo thứ tự khác.

**Bài 5 — Non-interference.** Sửa đoạn `list.stream().forEach(x -> list.add(x))` để tạo một danh sách kết quả mới mà không đụng vào source trong traversal.

**Bài 6 — Bộ đếm atomics.** Dùng `AtomicInteger` trong parallel `map` để đánh số element. Vì sao có thể không mất lượt tăng mà vẫn gắn số thứ tự sai so với encounter order?

**Bài 7 — collect vs forEach.** Sửa `parallelStream().forEach(result::add)` với `result` là `ArrayList` thành pipeline trả về List kết quả. Nếu cần một mutable `ArrayList` đúng kiểu, dùng collector nào?

**Bài 8 — Thứ tự terminal action.** So sánh `parallelStream().forEach(System.out::println)` và `parallelStream().forEachOrdered(System.out::println)`. Phần nào được bảo đảm thứ tự, phần nào không?

**Bài 9 — I/O stream.** Viết `try-with-resources` cho `Files.lines(path)`; dùng terminal `count` rồi bảo đảm resource được đóng cả khi exception phát sinh.

**Bài 10 — Test đáng tin.** Viết test chỉ kiểm tra `output.equals(List.of(...))` cho pipeline filter/map. Giải thích vì sao số lần `peek` không phải điều kiện pass.

**Bài 11 — Công cụ quan sát.** Nếu cần đếm số request gửi sang remote API, bạn nên instrument ở `peek` hay tại boundary thực sự gửi request? Làm thế nào để phân biệt attempt, success và committed result?

**Bài 12 — Bài toán thiết kế.** Một hệ thống muốn chạy song song để tính tổng giá trị order và cập nhật DB cho từng order. Hãy tách phần calculation thuần bằng Stream từ phần persistence có transaction/retry rõ ràng. Vì sao gộp cả hai vào `map` hoặc `peek` dễ gây khó kiểm soát?

## 23. Tổng kết

- **Stream pipeline là mô tả tính toán lazy**, không phải bản ghi từng bước chắc chắn xảy ra.
- Tài liệu Stream cho phép **tối ưu hóa và loại bỏ stages** khi giữ nguyên kết quả chính. `count()` trên nguồn biết kích thước là ví dụ quan trọng.
- **`peek` dành chủ yếu cho debug**. Nó không là audit hook, validation hook hay cơ chế điều phối side effects đáng tin.
- **Short-circuiting** có thể khiến các phần tử không được xử lý bởi callbacks phía sau; không dựa vào số lần gọi callback để xác định nghiệp vụ.
- **Parallel streams** không bảo đảm thứ tự/thời điểm/thread chạy intermediate actions; kết quả có encounter order không biến side-effect logs thành ordered logs.
- **`forEachOrdered` bảo đảm thứ tự terminal action** khi nguồn có encounter order, không bảo đảm mọi upstream side effects cùng thứ tự.
- **Non-interference và statelessness** là yêu cầu nền tảng cho behavioral parameters. `AtomicInteger` không sửa được mọi sai lệch do thứ tự scheduling.
- Dùng **`collect`, `toList`, `reduce`, `sum`, `count`** khi mục tiêu là dữ liệu; chọn vòng lặp hoặc quy trình xử lý tường minh khi side effect là mục tiêu chính.
- Stream từ file/channel thường cần **try-with-resources**; terminal operation không thay thế quản lý resource.
- Test **kết quả được API bảo đảm**, không test số dòng `peek` hay thread names như một phần contract.
- Các khái niệm này vẫn là kiến thức Java hiện hành. Ví dụ dùng Java 17+; khi dùng `List.of`, `toList` hay `String.isBlank/strip`, cần giữ đúng baseline JDK.

## 24. Tài liệu chính thức còn áp dụng

1. Java SE 25 API — `Stream`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
2. Java SE 25 API — `java.util.stream` package, mục **Non-interference**, **Stateless behaviors**, **Side-effects**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
3. Java SE 17 API — `Stream.count()`, `Stream.peek()` và `forEachOrdered()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
4. Java SE 17 API — `Collectors`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html
5. Java SE 17 API — `BaseStream`, `close()`, `onClose()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html
6. Java SE 17 API — `Files.lines(Path)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
7. Java SE 17 API — `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
8. Java SE 17 API — `List` và tính chất `Stream.toList()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html

Khi xem xét một Stream pipeline thực tế, hãy xác định trước **điều gì thuộc kết quả/hành vi được API hứa** và **điều gì chỉ là dấu vết phụ của một kế hoạch thực thi**. Chính sự phân biệt này giúp code đúng, dễ bảo trì và ít bất ngờ khi đổi JDK, tăng dữ liệu hoặc chuyển sang parallel execution.