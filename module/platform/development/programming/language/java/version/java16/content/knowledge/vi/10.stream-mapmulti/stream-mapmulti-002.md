# Vai trò BiConsumer, mapper và consumer phát phần tử

Trong `Stream.mapMulti`, mapper nhận hai đối số: phần tử nguồn hiện tại và một `Consumer` dùng để phát các phần tử kết quả xuống phần còn lại của pipeline. Kiểu hàm của mapper là `BiConsumer`, vì vậy mapper nhận hai đầu vào và không trả về giá trị trực tiếp. Mỗi lần gọi `Consumer.accept` sẽ phát thêm một phần tử; không gọi lần nào thì phần tử nguồn không tạo ra kết quả.

Hiểu đúng vai trò của ba thành phần này giúp viết `mapMulti` rõ ràng, kiểm soát được số kết quả và tránh nhầm lẫn với `map` hoặc `flatMap`.

## 1. Ba thành phần phối hợp với nhau

Một lời gọi `mapMulti` có ba thành phần:

- **Phần tử nguồn (`T`)**: giá trị hiện tại mà Stream đưa vào mapper.
- **Mapper (`BiConsumer`)**: đoạn xử lý quyết định có phát kết quả nào và phát những giá trị nào.
- **Consumer phát kết quả (`Consumer<R>`)**: kênh để mapper gửi từng giá trị kiểu `R` xuống pipeline.

Có thể hình dung luồng xử lý như sau:

```text
Phần tử nguồn T
      |
      v
  mapper.accept(T, emit)
      |
      +---- emit.accept(R1) ----> phần tử R1 xuống pipeline
      |
      +---- emit.accept(R2) ----> phần tử R2 xuống pipeline
      |
      +---- không gọi emit ------> không có kết quả từ T
```

Mapper được gọi cho từng phần tử nguồn mà pipeline thực sự xử lý. Trong lần gọi đó, mapper có thể phát không, một hoặc nhiều giá trị. Những giá trị được phát tiếp tục đi qua các thao tác phía sau như `filter`, `map`, `sorted` hoặc terminal operation.

## 2. Vì sao mapper có kiểu BiConsumer?

`BiConsumer<T, U>` là functional interface trong `java.util.function`. Nó nhận hai đối số và thực hiện một hành động, không trả về kết quả:

```java
@FunctionalInterface
public interface BiConsumer<T, U> {
    void accept(T t, U u);
}
```

Với `mapMulti`, hai đối số lần lượt là phần tử nguồn và Consumer phát kết quả. Vì vậy mapper có thể viết dưới dạng lambda:

```java
(source, emit) -> {
    // đọc source
    // gọi emit.accept(...) khi cần phát kết quả
}
```

Tên `emit` chỉ là tên biến do người viết chọn. Có thể dùng `output`, `downstream` hoặc tên khác dễ hiểu hơn. Điều quan trọng là tham số thứ hai là Consumer nhận kiểu kết quả của Stream mới.

Mapper không trả về `R` và cũng không trả về một `Stream<R>`. Giá trị đầu ra được gửi qua Consumer. Đây là điểm khác biệt cốt lõi giữa `mapMulti` với `map` và `flatMap`.

## 3. Vai trò của phần tử nguồn

Tham số đầu tiên của mapper là một phần tử kiểu `T` lấy từ Stream nguồn. Mapper đọc dữ liệu này để quyết định kết quả cần phát.

Ví dụ, mỗi sự kiện hệ thống có tên dịch vụ, mức độ nghiêm trọng và trạng thái đã xử lý. Ta dùng kiểu dữ liệu sau trong các ví dụ tiếp theo:

```java
record SystemEvent(
    String service,
    String severity,
    boolean resolved
) {}
```

Trong mapper, `event` là phần tử nguồn hiện tại. Ta có thể đọc các thuộc tính của nó, kiểm tra điều kiện và tạo chuỗi thông báo tương ứng.

Không cần tự duyệt lại Stream nguồn trong mapper. Pipeline chịu trách nhiệm đưa từng phần tử đến callback; mapper chỉ xử lý phần tử được truyền vào lần gọi hiện tại.

## 4. Vai trò của Consumer phát kết quả

`Consumer<R>` là functional interface nhận một giá trị kiểu `R` thông qua phương thức:

```java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T t);
}
```

Trong `mapMulti`, Consumer này đóng vai trò kênh phát kết quả. Mỗi lần gọi `accept`, mapper gửi một phần tử xuống pipeline.

Ví dụ tối giản:

```java
List<Integer> numbers = List.of(1, 2, 3);

List<Integer> duplicated = numbers.stream()
    .<Integer>mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .toList();
```

Kết quả:

```text
[1, 2, 2, 4, 3, 6]
```

Mỗi số nguồn phát hai giá trị: chính nó và giá trị gấp đôi. Hai lần gọi `accept` tạo ra hai phần tử kết quả theo đúng thứ tự gọi.

Consumer không phải danh sách kết quả để mapper tự quản lý. Mapper chỉ gửi từng giá trị; Stream tiếp tục chuyển các giá trị đó qua những thao tác còn lại của pipeline.

## 5. Mapper quyết định số lượng và nội dung kết quả

Số lần gọi `accept` xác định một phần tử nguồn đóng góp bao nhiêu phần tử đầu ra:

| Cách mapper xử lý | Số kết quả từ phần tử nguồn |
|---|---:|
| Không gọi `emit.accept(...)` | 0 |
| Gọi `emit.accept(...)` một lần | 1 |
| Gọi `emit.accept(...)` nhiều lần | Nhiều |

Dùng kiểu `SystemEvent` đã khai báo ở trên, một sự kiện đã xử lý không tạo thông báo; sự kiện mức độ WARNING tạo một thông báo; sự kiện CRITICAL tạo hai thông báo:

```java
import java.util.List;

List<SystemEvent> events = List.of(
    new SystemEvent("payment", "WARNING", false),
    new SystemEvent("search", "CRITICAL", false),
    new SystemEvent("catalog", "INFO", true)
);

List<String> messages = events.stream()
    .<String>mapMulti((event, emit) -> {
        if (event.resolved()) {
            return;
        }

        emit.accept(event.service() + ": " + event.severity());

        if ("CRITICAL".equals(event.severity())) {
            emit.accept("Notify on-call for " + event.service());
        }
    })
    .toList();
```

Kết quả:

```text
[
  payment: WARNING,
  search: CRITICAL,
  Notify on-call for search
]
```

Lệnh `return` trong lambda chỉ kết thúc lần gọi mapper hiện tại. Nó không kết thúc toàn bộ Stream. Vì sự kiện `catalog` đã được xử lý, mapper không phát kết quả cho phần tử đó và pipeline tiếp tục với các phần tử nguồn còn lại.

## 6. Khai báo mapper thành biến BiConsumer

Không bắt buộc phải viết toàn bộ logic ngay bên trong lời gọi `mapMulti`. Có thể tách mapper thành một biến có kiểu `BiConsumer` để đặt tên, tái sử dụng hoặc kiểm thử riêng:

```java
import java.util.function.BiConsumer;
import java.util.function.Consumer;

BiConsumer<SystemEvent, Consumer<String>> toMessages =
    (event, emit) -> {
        if (event.resolved()) {
            return;
        }

        emit.accept(event.service() + ": " + event.severity());

        if ("CRITICAL".equals(event.severity())) {
            emit.accept("Notify on-call for " + event.service());
        }
    };

List<String> messages = events.stream()
    .<String>mapMulti(toMessages)
    .toList();
```

Ở đây:

- `SystemEvent` là kiểu phần tử nguồn.
- `Consumer<String>` là Consumer nhận các chuỗi đầu ra.
- `toMessages` là mapper thực hiện quy tắc chuyển đổi.
- `mapMulti(toMessages)` áp dụng mapper đó lên Stream.

Cách tách này hữu ích khi quy tắc phát kết quả dài hoặc cần được đặt tên theo nghiệp vụ. Với logic ngắn và chỉ dùng một lần, lambda trực tiếp thường dễ đọc hơn.

## 7. Hiểu chữ ký generic của mapMulti

Chữ ký tổng quát của phương thức trên `Stream<T>` là:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Có thể đọc từng phần như sau:

- `T`: kiểu phần tử của Stream hiện tại.
- `R`: kiểu phần tử của Stream kết quả.
- `BiConsumer`: mapper nhận hai đối số và không trả về giá trị.
- `? super T`: mapper có thể nhận kiểu `T` hoặc một kiểu cha của `T`.
- `? super Consumer<R>`: tham số thứ hai của mapper có thể nhận `Consumer<R>` hoặc một kiểu cha phù hợp của nó.
- `Stream<R>`: kiểu Stream được trả về sau thao tác trung gian.

Các wildcard `? super` cho phép truyền vào những mapper chấp nhận kiểu tổng quát hơn. Trong cách dùng thông thường, không cần tự khai báo wildcard ở lambda; trình biên dịch suy luận kiểu tham số từ Stream nguồn và kiểu kết quả.

Khi kiểu đầu ra khó suy luận, có thể ghi rõ kiểu `R` ngay trên lời gọi:

```java
Stream<String> labels = events.stream()
    .<String>mapMulti((event, emit) -> {
        emit.accept(event.service());
    });
```

Cách viết `.<String>mapMulti` là type witness: nó chỉ rõ kiểu phần tử của Stream kết quả là `String`.

## 8. Consumer phát kết quả và các thao tác phía sau

Giá trị được gửi qua Consumer trở thành đầu vào cho những thao tác tiếp theo trong pipeline. Ví dụ:

```java
List<String> criticalServices = events.stream()
    .<String>mapMulti((event, emit) -> {
        if ("CRITICAL".equals(event.severity())) {
            emit.accept(event.service());
        }
    })
    .map(String::toUpperCase)
    .toList();
```

Trong pipeline này:

1. Mapper kiểm tra từng sự kiện.
2. Consumer chỉ phát tên dịch vụ của sự kiện CRITICAL.
3. `map(String::toUpperCase)` nhận từng tên dịch vụ đã phát và chuyển thành chữ hoa.
4. `toList()` tiêu thụ pipeline và tạo danh sách kết quả.

Mapper chỉ chịu trách nhiệm phát các giá trị phù hợp. Những thao tác xử lý tiếp theo vẫn có thể được viết thành các bước Stream riêng để giữ pipeline dễ đọc.

## 9. Các phiên bản Consumer cho kiểu nguyên thủy

Ngoài `mapMulti`, Stream API có ba phương thức chuyên biệt cho kiểu nguyên thủy. Chúng dùng Consumer tương ứng để phát giá trị mà không cần đóng gói thành object:

| Phương thức | Consumer nhận giá trị | Stream kết quả |
|---|---|---|
| `mapMultiToInt` | `IntConsumer` | `IntStream` |
| `mapMultiToLong` | `LongConsumer` | `LongStream` |
| `mapMultiToDouble` | `DoubleConsumer` | `DoubleStream` |

Ví dụ dùng `mapMultiToInt` để phát các chữ số trong mã dạng chuỗi:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305");

int digitSum = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int i = 0; i < code.length(); i++) {
            char ch = code.charAt(i);

            if (Character.isDigit(ch)) {
                emit.accept(Character.digit(ch, 10));
            }
        }
    })
    .sum();
```

Mỗi chữ số hợp lệ được gửi qua `IntConsumer.accept(int)`. `sum()` tính tổng trực tiếp trên `IntStream`.

Các Consumer chuyên biệt có cùng vai trò với `Consumer<R>`: nhận từng giá trị đầu ra. Khác biệt là chúng nhận kiểu nguyên thủy tương ứng, phù hợp với các phép toán số học tiếp theo.

## 10. Phạm vi sử dụng và tính an toàn của Consumer

Consumer được truyền vào mapper để phát kết quả trong lần gọi mapper hiện tại. Hãy gọi `accept` ngay trong callback và không giữ tham chiếu để gọi sau khi callback đã kết thúc. Consumer là cơ chế nối mapper với pipeline, không phải đối tượng phát sự kiện tùy ý có vòng đời độc lập.

Với parallel Stream, mapper của các phần tử nguồn khác nhau có thể được thực thi đồng thời. Vì vậy:

- Không lưu Consumer vào biến dùng chung giữa các lần gọi mapper.
- Không gọi Consumer từ một tác vụ bất đồng bộ chạy sau callback.
- Tránh cập nhật collection hoặc trạng thái mutable dùng chung trong mapper.
- Nếu mapper cần dữ liệu phụ, ưu tiên dữ liệu bất biến hoặc trạng thái cục bộ của lần gọi.

Mỗi lần mapper được gọi cần xử lý phần tử được truyền vào và phát các kết quả tương ứng. Điều này giúp pipeline hoạt động đúng khi chạy tuần tự hoặc song song.

## 11. Lazy evaluation và thời điểm mapper được gọi

`mapMulti` là thao tác trung gian. Việc gọi `mapMulti` chỉ thiết lập một bước trong pipeline; mapper được thực thi khi terminal operation bắt đầu tiêu thụ dữ liệu.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Stream;

Stream<String> labels = events.stream()
    .<String>mapMulti((event, emit) -> {
        System.out.println("Processing " + event.service());
        emit.accept(event.service());
    });

// Chưa có dòng "Processing ..." nào được in ra tại đây.

List<String> result = labels.toList();
// Mapper được thực thi khi toList() tiêu thụ Stream.
```

Nếu terminal operation có thể dừng sớm, chẳng hạn `findFirst()` hoặc `anyMatch(...)`, pipeline có thể không cần xử lý mọi phần tử nguồn. Vì thế không nên dựa vào mapper để thực hiện một tác dụng phụ bắt buộc phải xảy ra đúng một lần cho mọi phần tử.

## 12. Những nhầm lẫn thường gặp

**Nghĩ rằng mapper phải return một giá trị.** Mapper của `mapMulti` là `BiConsumer`, nên không trả về kết quả. Hãy gọi Consumer để phát từng giá trị.

**Nhầm Consumer với phần tử nguồn.** Tham số đầu tiên chứa dữ liệu đầu vào kiểu `T`; tham số thứ hai nhận dữ liệu đầu ra kiểu `R`. Hai tham số có vai trò và kiểu dữ liệu khác nhau.

**Chỉ gọi accept một lần vì nghĩ Consumer chỉ nhận được một giá trị.** Một Consumer có thể nhận nhiều lần gọi `accept` trong cùng lần mapper chạy. Mỗi lần gọi tạo thêm một phần tử đầu ra.

**Cho rằng không gọi accept là lỗi.** Không gọi Consumer là cách hợp lệ để phần tử nguồn tạo ra không phần tử đầu ra.

**Tự thu thập kết quả vào danh sách dùng chung.** Việc phát kết quả đã được Consumer đảm nhiệm. Thu thập vào collection bên ngoài vừa trùng trách nhiệm với pipeline, vừa dễ gây lỗi khi Stream chạy song song.

**Giữ Consumer để gọi sau.** Hãy dùng Consumer trong chính lần gọi mapper. Không xem nó như callback có thể lưu và sử dụng ở thời điểm khác.

## 13. Ghi nhớ khi đọc và viết mapMulti

Khi gặp một lời gọi `mapMulti`, hãy xác định rõ ba điều:

1. Phần tử nguồn có kiểu gì và mapper đọc dữ liệu nào từ nó?
2. Consumer nhận kiểu kết quả nào?
3. Những nhánh nào gọi `accept`, và mỗi nhánh phát bao nhiêu phần tử?

Mapper là nơi quyết định quy tắc biến đổi. `BiConsumer` mô tả callback nhận phần tử nguồn cùng Consumer phát kết quả. Consumer chuyển từng giá trị đầu ra xuống pipeline. Khi tách bạch được ba vai trò này, ta có thể đọc, viết và bảo trì các phép biến đổi một-nhiều bằng `mapMulti` một cách chính xác.

