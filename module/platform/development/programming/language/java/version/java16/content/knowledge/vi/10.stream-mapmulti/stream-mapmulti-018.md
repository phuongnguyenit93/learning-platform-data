# Yêu cầu stateless, non-interfering và bẫy trạng thái dùng chung khi parallel

Mapper truyền cho `Stream.mapMulti` là một behavioral parameter: nó mô tả cách chuyển mỗi phần tử nguồn thành không, một hoặc nhiều phần tử đầu ra. Theo hợp đồng Stream API, behavioral parameters cần **stateless** và **non-interfering**. Điều này đặc biệt quan trọng khi pipeline chạy song song, vì mapper của nhiều phần tử có thể được thực thi đồng thời và không theo thứ tự encounter order.

Một mapper an toàn thường chỉ dựa vào phần tử hiện tại cùng cấu hình bất biến, rồi phát kết quả trực tiếp qua Consumer. Không sửa nguồn đang được duyệt và không dùng biến, collection hay object mutable dùng chung để phối hợp giữa các lần gọi mapper.

## 1. Stateless nghĩa là gì?

Một mapper là *stateless* khi kết quả xử lý một phần tử không phụ thuộc vào trạng thái có thể thay đổi trong lúc pipeline chạy.

Ví dụ stateless: mỗi số phát chính nó và bình phương của nó:

```java
import java.util.stream.IntStream;

int[] values = IntStream.of(2, 3, 4)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * number);
    })
    .toArray();
```

Kết quả từ mỗi phần tử chỉ phụ thuộc vào chính số đó. Xử lý số 2 không làm thay đổi kết quả xử lý số 3.

Một mapper có thể đọc cấu hình bất biến được tạo trước pipeline. Ví dụ:

```java
import java.util.Set;
import java.util.stream.IntStream;

Set<Integer> allowed = Set.of(2, 3, 5, 7);

int[] selected = IntStream.of(1, 2, 3, 4, 5, 6, 7)
    .mapMulti((number, emit) -> {
        if (allowed.contains(number)) {
            emit.accept(number);
        }
    })
    .toArray();
```

Tập `allowed` không thay đổi trong lúc Stream chạy. Kết quả của mỗi phần tử chỉ phụ thuộc vào giá trị nguồn và cấu hình ổn định này.

Stateless không có nghĩa là trong mapper tuyệt đối không được khai báo biến cục bộ. Một object mutable được tạo mới trong từng lần gọi mapper và chỉ dùng trong lần gọi đó có thể an toàn vì không bị chia sẻ giữa các phần tử:

```java
import java.util.List;

record Person(String firstName, String lastName) {}

List<Person> people = List.of(
    new Person("An", "Nguyen"),
    new Person("Binh", "Tran")
);

List<String> labels = people.stream()
    .<String>mapMulti((person, emit) -> {
        StringBuilder label = new StringBuilder();

        label.append(person.lastName())
            .append(", ")
            .append(person.firstName());

        emit.accept(label.toString());
    })
    .toList();
```

Mỗi mapper invocation tạo một `StringBuilder` riêng. Builder không được lưu ra ngoài hoặc chia sẻ với phần tử khác; đầu ra được phát dưới dạng `String`.

## 2. Stateful mapper làm kết quả phụ thuộc vào lần xử lý trước

Một mapper trở thành *stateful* khi nó đọc hoặc thay đổi trạng thái dùng chung giữa các lần gọi.

Ví dụ dùng mảng làm bộ đếm:

```java
import java.util.stream.IntStream;

int[] counter = {0};

int[] sequence = IntStream.of(10, 20, 30, 40)
    .mapMulti((number, emit) -> {
        emit.accept(++counter[0]);
    })
    .toArray();
```

Kết quả phụ thuộc vào số lần mapper đã chạy trước đó. Giá trị được phát cho một phần tử không còn được xác định chỉ bởi phần tử nguồn.

Với Stream tuần tự, ví dụ có thể tình cờ tạo dãy 1, 2, 3, 4. Nhưng nếu đổi sang parallel Stream, các lần gọi mapper có thể diễn ra đồng thời và thứ tự thực thi không được bảo đảm. Mảng đếm còn có nguy cơ race condition vì phép tăng không phải thao tác nguyên tử.

Không nên dựa vào thứ tự mapper được gọi để gán số thứ tự, phân bổ mã hoặc tạo trạng thái tích lũy. Nếu nghiệp vụ cần chỉ số ổn định, hãy đưa chỉ số vào dữ liệu nguồn hoặc dùng một phép biến đổi thuần dựa trên chỉ số đó.

## 3. AtomicInteger không biến mapper stateful thành stateless

Có thể thay mảng đếm bằng `AtomicInteger` để tránh race condition khi tăng bộ đếm:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger counter = new AtomicInteger();

int[] sequence = IntStream.of(10, 20, 30, 40)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(counter.incrementAndGet());
    })
    .toArray();
```

`AtomicInteger` bảo đảm mỗi lần tăng là nguyên tử, nhưng mapper vẫn phụ thuộc vào trạng thái thay đổi dùng chung. Giá trị nào được gán cho số nguồn nào phụ thuộc lịch thực thi song song; kết quả có thể khác nhau giữa các lần chạy.

Thread-safe và stateless là hai yêu cầu khác nhau:

- **Thread-safe** nói về việc truy cập đồng thời có tránh được race condition hay không.
- **Stateless** nói về việc kết quả xử lý một phần tử có phụ thuộc trạng thái thay đổi từ những lần xử lý khác hay không.

Dùng `AtomicInteger` có thể giải quyết tranh chấp cập nhật bộ đếm, nhưng không làm kết quả của mapper độc lập theo từng phần tử. Nếu cần thứ tự xác định, hãy thiết kế lại dữ liệu đầu vào để chứa chỉ số hoặc mã đã được gán trước khi chạy pipeline.

## 4. Cách sai: sửa collection nguồn trong mapper

*Non-interfering* nghĩa là không can thiệp bằng cách sửa nguồn dữ liệu trong khi pipeline đang tiêu thụ nguồn đó, trừ trường hợp nguồn được thiết kế rõ ràng để hỗ trợ sửa đổi đồng thời theo hợp đồng riêng.

Ví dụ sau sửa chính `List` đang được duyệt:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

List<Integer> expanded = source.stream()
    .<Integer>mapMulti((number, emit) -> {
        emit.accept(number);

        if (number == 2) {
            source.add(4);
        }
    })
    .toList();
```

Mapper gọi `source.add(4)` trong lúc Stream đang duyệt `source`. Với collection thông thường như `ArrayList`, việc này có thể gây `ConcurrentModificationException` hoặc làm hành vi duyệt không còn hợp lệ theo yêu cầu non-interference.

Cách đúng là phát dữ liệu ra pipeline và thu kết quả riêng:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

List<Integer> expanded = source.stream()
    .<Integer>mapMulti((number, emit) -> {
        emit.accept(number);

        if (number == 2) {
            emit.accept(4);
        }
    })
    .toList();
```

Nếu cần cập nhật collection sau khi xử lý xong, hãy làm ở bước riêng sau terminal operation. Không thay đổi cấu trúc nguồn trong lúc Stream đang duyệt nó.

## 5. Không sửa object thuộc nguồn đang được xử lý

Can thiệp nguồn không chỉ là thêm hoặc xóa phần tử khỏi collection. Thay đổi trạng thái của các object trong nguồn trong khi pipeline đang chạy cũng có thể khiến kết quả phụ thuộc thứ tự và thời điểm thực thi.

Ví dụ không nên làm:

```java
import java.util.List;

class Account {
    private long balance;

    Account(long balance) {
        this.balance = balance;
    }

    long balance() {
        return balance;
    }

    void addBonus(long amount) {
        balance += amount;
    }
}

List<Account> accounts = List.of(
    new Account(1_000L),
    new Account(2_000L)
);

long[] balances = accounts.stream()
    .mapMultiToLong((account, emit) -> {
        account.addBonus(100L);
        emit.accept(account.balance());
    })
    .toArray();
```

Mapper vừa thay đổi object nguồn vừa phát giá trị. Nếu cùng object còn được sử dụng ở nơi khác hoặc nhiều tác vụ đọc nó đồng thời, kết quả có thể phụ thuộc thời điểm và gây race condition.

Thiết kế an toàn hơn là tạo giá trị kết quả mới mà không sửa object đầu vào:

Tiếp tục dùng lớp `Account` và danh sách `accounts` đã khai báo trong ví dụ trên:

```java
long[] adjustedBalances = accounts.stream()
    .mapMultiToLong((account, emit) -> {
        emit.accept(account.balance() + 100L);
    })
    .toArray();
```

Phép tính chỉ đọc số dư hiện tại và phát một giá trị mới. `Account` không bị thay đổi trong pipeline.

## 6. Bẫy shared mutable state khi dùng parallel Stream

Trong parallel Stream, nhiều mapper invocation có thể chạy trên các thread khác nhau cùng lúc. Nếu tất cả cùng ghi vào một collection mutable thông thường, chương trình có thể gặp race condition, mất phần tử hoặc làm hỏng cấu trúc collection.

Ví dụ không an toàn:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> sideEffects = new ArrayList<>();

int[] values = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .mapMulti((number, emit) -> {
        sideEffects.add(number);
        emit.accept(number);
    })
    .toArray();
```

`ArrayList` không hỗ trợ nhiều thread cùng thêm phần tử mà không có cơ chế đồng bộ. Các mapper có thể gọi `add` đồng thời, nên `sideEffects` có thể thiếu phần tử hoặc rơi vào trạng thái không mong muốn.

Dù thay `ArrayList` bằng collection thread-safe, việc ghi side effect dùng chung trong mapper vẫn khiến logic phụ thuộc trạng thái bên ngoài và thứ tự thực thi. Hãy để Stream thu thập kết quả thông qua terminal operation.

## 7. Dùng kết quả của pipeline thay cho collection side effect

Nếu mục tiêu là thu thập các giá trị được phát, hãy dùng `toList()` hoặc collector:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);
        if (number % 2 == 0) {
            emit.accept(-number);
        }
    })
    .boxed()
    .toList();
```

Stream framework quản lý việc kết hợp kết quả của các phần xử lý song song. Mapper không cần tự ghi vào một `ArrayList` dùng chung.

Nếu cần một `ArrayList` có thể sửa đổi sau khi thu thập, dùng collector:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);
    })
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));
```

Collector tạo các container tích lũy riêng cho các phần xử lý và kết hợp chúng theo hợp đồng Collector. Không cần chia sẻ một `ArrayList` bên ngoài giữa các mapper.

Với primitive Stream, cũng có thể dùng các terminal operation chuyên biệt như `sum()`, `count()`, `summaryStatistics()` hoặc `toArray()` thay vì tạo collection wrapper chỉ để tổng hợp số.

## 8. Tính tổng và thống kê bằng reduction thay vì bộ đếm dùng chung

Không cập nhật một biến tổng dùng chung bên trong mapper:

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.IntStream;

AtomicLong total = new AtomicLong();

IntStream.rangeClosed(1, 1_000)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);
        total.addAndGet(number);
    })
    .toArray();

long result = total.get();
```

Dù `AtomicLong` bảo vệ phép cộng, mapper vẫn có side effect và phụ thuộc trạng thái dùng chung. Nếu mục tiêu là tính tổng các số, hãy phát dữ liệu vào pipeline rồi dùng reduction:

```java
import java.util.stream.IntStream;

long total = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);
    })
    .asLongStream()
    .sum();
```

Nếu mỗi số phát nhiều kết quả, reduction vẫn áp dụng sau mapper:

```java
import java.util.stream.IntStream;

long total = IntStream.rangeClosed(1, 100)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);
        if (number % 2 == 0) {
            emit.accept(number * 10);
        }
    })
    .asLongStream()
    .sum();
```

Kết quả tổng được tính từ các giá trị do pipeline phát ra. Cách này thể hiện mục tiêu trực tiếp và cho phép Stream framework thực hiện reduction phù hợp với xử lý song song.

Lưu ý: `IntStream.sum()` cộng bằng kiểu `int` và có thể tràn. Chuyển sang `LongStream` trước khi tổng hợp nếu phạm vi tổng có thể vượt `int`. `LongStream.sum()` cũng có thể tràn nếu tổng vượt giới hạn `long`; khi cần tổng chính xác lớn hơn, dùng `BigInteger`.

## 9. Thứ tự thực thi mapper không phải encounter order

Với một Stream có encounter order, một số terminal operation như `toList()` và `toArray()` bảo toàn thứ tự phần tử kết quả theo encounter order. Tuy nhiên, điều đó không có nghĩa mapper trong parallel Stream được gọi theo thứ tự nguồn.

Ví dụ, mỗi số phát chính nó và số âm tương ứng nếu là số chẵn:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 4)
    .parallel()
    .mapMulti((number, emit) -> {
        emit.accept(number);

        if (number % 2 == 0) {
            emit.accept(-number);
        }
    })
    .boxed()
    .toList();
```

Với nguồn có encounter order và terminal operation bảo toàn thứ tự, danh sách kết quả là `[1, 2, -2, 3, 4, -4]`. Mapper của số 4 vẫn có thể bắt đầu hoặc hoàn tất trước mapper của số 2.

Do đó:

- Không dùng thứ tự gọi mapper để gán số thứ tự hoặc tạo timestamp nghiệp vụ.
- Không giả định side effect xảy ra theo encounter order.
- Nếu cần kết quả có thứ tự, dùng nguồn có encounter order và terminal operation bảo toàn thứ tự.
- Nếu dùng `unordered()`, không dựa vào thứ tự kết quả.

`forEachOrdered()` có thể yêu cầu hành động terminal được thực hiện theo encounter order, nhưng không biến mapper thành stateful callback an toàn và cũng không làm cho việc sửa nguồn trở nên hợp lệ.

## 10. Stateless mapper với nhiều lần phát trong parallel

Một mapper có thể phát nhiều giá trị cho một phần tử và vẫn stateless nếu mọi kết quả chỉ phụ thuộc phần tử hiện tại cùng dữ liệu cấu hình bất biến.

```java
import java.util.List;
import java.util.Set;

record OrderLine(String sku, int quantity) {}

List<OrderLine> lines = List.of(
    new OrderLine("BOOK-01", 2),
    new OrderLine("PEN-02", 3),
    new OrderLine("BAG-03", 1)
);

Set<String> trackedSkus = Set.of("BOOK-01", "BAG-03");

List<String> events = lines.parallelStream()
    .<String>mapMulti((line, emit) -> {
        if (trackedSkus.contains(line.sku())) {
            for (int index = 0; index < line.quantity(); index++) {
                emit.accept(line.sku() + "#" + (index + 1));
            }
        }
    })
    .toList();
```

Mỗi lần mapper chỉ đọc một `OrderLine`, đọc tập `trackedSkus` bất biến và phát các chuỗi kết quả. Không có trạng thái được cập nhật để ảnh hưởng đến mapper của dòng hàng khác.

Vì `lines` có encounter order và `toList()` bảo toàn thứ tự, danh sách kết quả cũng giữ thứ tự dòng hàng và thứ tự phát trong từng dòng. Việc thực thi mapper vẫn có thể diễn ra song song.

## 11. Khi nào dùng collect, reduce hoặc stateful component riêng?

Hãy chọn cơ chế theo mục tiêu:

| Mục tiêu | Cách phù hợp |
|---|---|
| Phát và biến đổi từng phần tử độc lập | `mapMulti` với mapper stateless |
| Tính tổng số nguyên | `sum()` hoặc `mapToLong(...).sum()` |
| Tính min, max, average và count | `summaryStatistics()` |
| Thu kết quả thành danh sách | `toList()` hoặc `collect(...)` |
| Gộp dữ liệu theo khóa | `Collectors.groupingBy(...)` hoặc collector phù hợp |
| Tính một kết quả kết hợp từ các phần tử | `reduce(...)` với accumulator/combiner phù hợp |
| Quản lý trạng thái có thứ tự hoặc phụ thuộc phần tử trước | Vòng lặp hoặc stateful component được thiết kế rõ ràng |

`reduce` yêu cầu identity, accumulator và combiner tuân thủ hợp đồng kết hợp; không dùng một accumulator có side effect hoặc phụ thuộc trạng thái ngoài. Với bài toán thu thập nhiều phần tử, collector thường phù hợp hơn việc tự quản lý một collection dùng chung.

Nếu thuật toán thực sự cần phần tử trước để tính phần tử sau, chẳng hạn tạo số thứ tự tuần tự hoặc tính trạng thái tích lũy có ý nghĩa nghiệp vụ, hãy cân nhắc vòng lặp tuần tự rõ ràng. Không ép một thuật toán stateful vào parallel Stream bằng biến mutable hoặc atomic counter.

## 12. Các nguyên tắc áp dụng cho Stream và primitive Stream

Yêu cầu stateless và non-interfering không chỉ áp dụng cho `Stream<T>.mapMulti`. Nó cũng áp dụng cho các behavioral parameter của các thao tác Stream khác và các biến thể primitive:

| Phương thức | Mapper/Consumer | Kiểu kết quả |
|---|---|---|
| `Stream<T>.mapMulti` | `BiConsumer` và `Consumer<R>` | `Stream<R>` |
| `Stream<T>.mapMultiToInt` | `BiConsumer` và `IntConsumer` | `IntStream` |
| `Stream<T>.mapMultiToLong` | `BiConsumer` và `LongConsumer` | `LongStream` |
| `Stream<T>.mapMultiToDouble` | `BiConsumer` và `DoubleConsumer` | `DoubleStream` |
| `IntStream.mapMulti` | `IntMapMultiConsumer` và `IntConsumer` | `IntStream` |
| `LongStream.mapMulti` | `LongMapMultiConsumer` và `LongConsumer` | `LongStream` |
| `DoubleStream.mapMulti` | `DoubleMapMultiConsumer` và `DoubleConsumer` | `DoubleStream` |

Primitive Stream giảm nhu cầu boxing cho giá trị số, nhưng không tự làm cho mapper an toàn khi chạy song song. Một `IntConsumer` hoặc `LongConsumer` vẫn có thể được gọi từ nhiều lần mapper khác nhau trong quá trình xử lý parallel. Không dùng một mảng, bộ đếm hoặc collection mutable dùng chung chỉ vì đầu ra là primitive.

## 13. Checklist rà soát mapper trước khi chạy parallel

Trước khi chuyển pipeline sang `.parallel()` hoặc `.parallelStream()`, hãy kiểm tra:

1. **Kết quả có phụ thuộc phần tử trước không?** Nếu có, mapper đang dùng trạng thái hoặc thứ tự bên ngoài.
2. **Mapper có đọc mutable state dùng chung không?** Nếu state có thể thay đổi trong lúc pipeline chạy, kết quả có thể không ổn định.
3. **Mapper có ghi vào collection hoặc bộ đếm bên ngoài không?** Hãy chuyển việc thu thập sang terminal operation hoặc collector.
4. **Mapper có sửa nguồn hoặc object thuộc nguồn không?** Không can thiệp nguồn trong lúc đang duyệt.
5. **Có nhiều thread cùng sửa một object không?** Loại bỏ chia sẻ mutable hoặc thiết kế cơ chế đồng bộ riêng ở ngoài mapper.
6. **Thứ tự kết quả có quan trọng không?** Dùng nguồn có encounter order và terminal operation bảo toàn thứ tự khi cần.
7. **Có thể biểu diễn bằng reduction không?** Dùng `sum`, `summaryStatistics`, `reduce` hoặc collector thay cho stateful counter.
8. **Mapper có chỉ dựa vào phần tử hiện tại và cấu hình bất biến không?** Đây là dấu hiệu tốt của mapper stateless.

Không cần chọn parallel Stream chỉ vì có thể dùng. Nếu mapper có logic phụ thuộc trạng thái, dữ liệu ít hoặc chi phí xử lý nhỏ, Stream tuần tự hay vòng lặp rõ ràng có thể phù hợp hơn.

## 14. Lỗi thường gặp

**Dùng biến đếm bên ngoài mapper.** Mỗi phần tử làm thay đổi trạng thái chung, khiến mapper stateful và có thể tạo race condition. Hãy đưa chỉ số vào nguồn hoặc dùng phép reduction phù hợp.

**Thay biến thường bằng AtomicInteger rồi nghĩ mapper đã stateless.** Atomic chỉ bảo vệ cập nhật đồng thời; mapper vẫn phụ thuộc trạng thái thay đổi và việc gán giá trị cho từng phần tử không xác định theo thứ tự.

**Thêm phần tử vào collection nguồn trong mapper.** Đây là source interference và có thể gây lỗi khi duyệt. Hãy phát kết quả qua Consumer và thu riêng sau pipeline.

**Ghi vào ArrayList dùng chung trong parallel mapper.** ArrayList không an toàn cho cập nhật đồng thời. Dùng `toList()` hoặc collector để Stream quản lý việc thu thập.

**Cho rằng synchronized collection giải quyết mọi vấn đề.** Đồng bộ có thể bảo vệ cấu trúc dữ liệu, nhưng không làm mapper stateless, không bảo đảm thứ tự nghiệp vụ và có thể tạo nút thắt hiệu năng.

**Dựa vào thứ tự gọi mapper.** Parallel Stream không bảo đảm mapper chạy theo encounter order. Chỉ dựa vào thứ tự kết quả khi nguồn và terminal operation bảo toàn thứ tự.

**Cho rằng local mutable object luôn sai.** Object được tạo riêng trong mapper invocation, không chia sẻ và không làm thay đổi nguồn có thể an toàn. Vấn đề là trạng thái mutable dùng chung hoặc làm kết quả phụ thuộc lần gọi khác.

**Dùng side effect trong intermediate operation để ghi log hoặc cập nhật nghiệp vụ bắt buộc.** Pipeline có thể short-circuit hoặc tối ưu một số giai đoạn; không dựa vào mapper được gọi đúng một lần cho mọi phần tử để bảo đảm tác dụng phụ.

**Dùng double cho giá trị cần độ chính xác thập phân.** Primitive specialization không sửa sai số IEEE 754. Với tiền tệ hoặc số thập phân chính xác, chọn `BigDecimal` hoặc biểu diễn số nguyên theo đơn vị nhỏ nhất khi phù hợp.

## 15. Ghi nhớ

- Behavioral parameter của Stream, bao gồm mapper `mapMulti`, nên **stateless** và **non-interfering**.
- Stateless nghĩa là kết quả mỗi phần tử không phụ thuộc trạng thái thay đổi từ các lần xử lý khác.
- Non-interfering nghĩa là không sửa nguồn dữ liệu trong lúc pipeline đang tiêu thụ nguồn đó, trừ nguồn concurrent có hợp đồng riêng.
- Local mutable object có thể an toàn nếu được tạo riêng trong mapper và không bị chia sẻ hoặc làm thay đổi nguồn.
- Parallel Stream có thể chạy nhiều mapper đồng thời; không ghi vào mảng, bộ đếm hoặc collection mutable dùng chung.
- `AtomicInteger` và synchronized collection không tự biến mapper stateful thành stateless.
- Dùng `toList()`, collector, `sum()`, `summaryStatistics()` hoặc `reduce()` để thu thập và tổng hợp kết quả.
- Encounter order của kết quả không đồng nghĩa thứ tự thực thi mapper.
- Nếu thuật toán phụ thuộc trạng thái hoặc thứ tự phần tử trước, hãy dùng vòng lặp hoặc thiết kế stateful component riêng thay vì ép vào parallel mapper.

Một mapper `mapMulti` phù hợp cho parallel Stream khi từng lần gọi có thể xử lý độc lập: chỉ đọc phần tử hiện tại và dữ liệu cấu hình ổn định, phát kết quả qua Consumer, không sửa nguồn và không cập nhật trạng thái mutable dùng chung. Thiết kế như vậy giúp pipeline dễ dự đoán, an toàn hơn khi chạy song song và vẫn tận dụng được khả năng phát không, một hoặc nhiều phần tử của `mapMulti`.

