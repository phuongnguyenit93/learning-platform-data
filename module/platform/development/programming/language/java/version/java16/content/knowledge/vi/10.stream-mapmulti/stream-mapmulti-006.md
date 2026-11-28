# Dùng type witness để giải quyết suy luận kiểu kết quả

`Stream.mapMulti` là một generic method có kiểu đầu ra `R`. Mapper của nó nhận phần tử nguồn và một `Consumer<R>` để phát kết quả. Vì mapper không trả về `R` trực tiếp, có những trường hợp trình biên dịch không có đủ thông tin rõ ràng để suy luận kiểu kết quả theo ý định của người viết.

Java cho phép chỉ định tường minh tham số kiểu của lời gọi generic method bằng *type witness*. Với `mapMulti`, cú pháp là:

```java
source.<String>mapMulti((element, emit) -> {
    emit.accept("...");
});
```

Type witness `<String>` cho trình biên dịch biết Stream kết quả có kiểu phần tử là `String`. Đây là thông tin ở thời điểm biên dịch; nó không chuyển đổi dữ liệu khi chạy và cũng không phải phép ép kiểu.

## 1. Vì sao mapMulti có thể cần type witness?

Chữ ký tổng quát của `mapMulti` trên `Stream<T>` là:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Trong đó:

- `T` là kiểu phần tử của Stream nguồn.
- `R` là kiểu phần tử của Stream kết quả.
- Mapper có kiểu `BiConsumer`, nhận phần tử nguồn và Consumer phát kết quả.
- Consumer nhận từng giá trị kiểu `R` qua phương thức `accept`.

Với `map`, mapper trả về một giá trị. Kiểu của biểu thức trả về thường cung cấp thông tin trực tiếp để trình biên dịch suy luận kiểu đầu ra. Với `mapMulti`, mapper trả về `void`; các giá trị được gửi qua Consumer. Vì vậy, thông tin suy luận kiểu có thể ít rõ ràng hơn, nhất là khi có nhiều nhánh, nhánh không phát kết quả hoặc kiểu kết quả cần được xác định từ ngữ cảnh.

Type witness giúp chỉ rõ `R` ngay tại lời gọi phương thức, để kiểu của tham số Consumer trong lambda được xác định rõ.

## 2. Cú pháp type witness trong lời gọi mapMulti

Type witness được đặt sau dấu chấm và trước tên phương thức:

```java
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3);

Stream<String> labels = stream.<String>mapMulti((element, emit) -> {
    emit.accept(element.toString());
});
```

Có thể đọc lời gọi trên như sau:

- `stream` là Stream nguồn.
- `<String>` chỉ định tham số kiểu `R` của generic method.
- `mapMulti(...)` nhận mapper có Consumer phát các giá trị kiểu `String`.

Khi gọi theo chuỗi, type witness vẫn nằm ngay trước `mapMulti`:

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

List<String> labels = values.stream()
    .<String>mapMulti((value, emit) -> {
        emit.accept("value=" + value);
    })
    .toList();
```

Cú pháp đúng là `.<String>mapMulti(...)`. Không viết `mapMulti<String>(...)`, vì Java đặt tham số kiểu của lời gọi generic method trước tên phương thức trong trường hợp này.

## 3. Ví dụ: chỉ rõ kiểu kết quả là String

Giả sử mỗi phép đo có thể tạo ra cảnh báo dạng chuỗi. Ta muốn biến một Stream các phép đo thành Stream<String>:

```java
import java.util.List;

record Reading(String sensorId, double temperature) {}

List<Reading> readings = List.of(
    new Reading("S-01", 25.0),
    new Reading("S-02", 82.5),
    new Reading("S-03", 91.0)
);

var alerts = readings.stream()
    .<String>mapMulti((reading, emit) -> {
        if (reading.temperature() >= 80.0) {
            emit.accept(
                reading.sensorId() + ": high temperature"
            );
        }
    })
    .toList();
```

Kiểu của `alerts` là `List<String>`, vì type witness xác định `R` là `String`. Phép đo có nhiệt độ dưới ngưỡng không gọi `emit.accept`, nên không đóng góp phần tử đầu ra.

Ở đây, `var` chỉ suy luận kiểu biến từ kiểu biểu thức bên phải. Nó không chỉ định kiểu kết quả cho lời gọi `mapMulti`. Type witness đã cung cấp thông tin đó trước khi kiểu của danh sách được xác định.

## 4. Khi nào nên chỉ định kiểu tường minh?

Không phải mọi lời gọi `mapMulti` đều bắt buộc phải có type witness. Nếu kiểu kết quả được suy luận rõ ràng từ các giá trị phát ra và ngữ cảnh sử dụng, có thể bỏ phần chỉ định kiểu.

Tuy nhiên, nên cân nhắc type witness trong các tình huống sau:

- Lambda có nhiều nhánh, đặc biệt khi không có nhánh nào phát giá trị đủ để trình biên dịch suy ra kiểu `R`.
- Các giá trị được phát thuộc những kiểu con khác nhau và cần một kiểu cha hoặc interface chung làm kiểu Stream kết quả.
- Kiểu của biểu thức được lưu bằng `var`, nên không có kiểu đích ở phía trái để giúp suy luận.
- Lời gọi nằm trong một biểu thức generic hoặc một chuỗi thao tác mà kiểu kết quả không rõ khi đọc mã.
- Trình biên dịch báo lỗi suy luận kiểu hoặc suy ra kiểu rộng hơn mong muốn.

Type witness làm rõ hợp đồng kiểu ngay tại nơi phát sinh kết quả. Điều này cũng giúp người đọc hiểu được Stream mới chứa loại dữ liệu nào mà không cần lần theo mọi nhánh trong mapper.

## 5. Nhánh không phát kết quả vẫn có kiểu đầu ra

Một mapper có thể không gọi Consumer trong một số trường hợp. Điều đó không có nghĩa Stream kết quả không có kiểu phần tử. Kiểu `R` vẫn phải được xác định cho toàn bộ Stream.

Ví dụ, chỉ phát mã lỗi khi trạng thái không hợp lệ:

```java
import java.util.List;

record ValidationResult(String field, boolean valid) {}

List<ValidationResult> results = List.of(
    new ValidationResult("email", true),
    new ValidationResult("phone", false),
    new ValidationResult("address", true)
);

List<String> invalidFields = results.stream()
    .<String>mapMulti((result, emit) -> {
        if (!result.valid()) {
            emit.accept(result.field());
        }
    })
    .toList();
```

Stream kết quả luôn có kiểu phần tử là `String`, dù một số phần tử nguồn không phát ra giá trị nào. Type witness chỉ định kiểu cho toàn bộ Stream, không chỉ cho nhánh có gọi `accept`.

Điểm này hữu ích khi mapper có nhiều nhánh điều kiện. Người viết có thể chỉ rõ kiểu kết quả một lần, thay vì trông chờ trình biên dịch suy luận từ từng lời gọi `accept`.

## 6. Chọn kiểu chung khi phát các kiểu con khác nhau

Một Consumer có thể nhận các giá trị thuộc những kiểu con của kiểu kết quả `R`. Khi muốn Stream kết quả có kiểu chung, hãy chỉ rõ kiểu chung bằng type witness.

Ví dụ, cả `String` và `StringBuilder` đều triển khai `CharSequence`:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(10, 20);

Stream<CharSequence> descriptions = numbers.stream()
    .<CharSequence>mapMulti((number, emit) -> {
        emit.accept("number=" + number);
        emit.accept(
            new StringBuilder("value length=" + number.toString().length())
        );
    });
```

Stream kết quả có kiểu `Stream<CharSequence>`. Consumer có thể nhận cả đối tượng `String` và `StringBuilder` vì cả hai đều có thể được gán cho kiểu `CharSequence`.

Nếu không chỉ định kiểu chung, trình biên dịch có thể suy luận một kiểu khác với kiểu mà API phía sau mong muốn. Chọn kiểu kết quả phù hợp với hợp đồng của pipeline giúp các thao tác tiếp theo sử dụng dữ liệu nhất quán.

## 7. Type witness và kiểu đích của biểu thức

Java có cơ chế target typing: kiểu mà biểu thức được gán hoặc truyền vào có thể tham gia quá trình suy luận kiểu generic. Ví dụ:

Tiếp tục dùng kiểu `Reading` và biến `readings` đã khai báo ở ví dụ trước:

```java
import java.util.stream.Stream;

Stream<String> labels = readings.stream()
    .mapMulti((reading, emit) -> {
        if (reading.temperature() >= 80.0) {
            emit.accept(reading.sensorId());
        }
    });
```

Trong một ngữ cảnh có kiểu đích rõ như trên, trình biên dịch có thể sử dụng kiểu `Stream<String>` mong đợi để suy luận kiểu kết quả. Tuy nhiên, mức độ suy luận còn phụ thuộc vào cấu trúc biểu thức và các ràng buộc kiểu trong lambda.

Khi muốn mã rõ ràng, ổn định và ít phụ thuộc vào ngữ cảnh suy luận, có thể viết:

```java
Stream<String> labels = readings.stream()
    .<String>mapMulti((reading, emit) -> {
        if (reading.temperature() >= 80.0) {
            emit.accept(reading.sensorId());
        }
    });
```

Hai cách đều có thể phù hợp. Type witness là lựa chọn chủ động để nói rõ kiểu kết quả tại lời gọi phương thức; nó không thay thế cơ chế target typing của Java.

## 8. Khai báo mapper thành biến có kiểu cụ thể

Một cách khác để cung cấp thông tin kiểu là khai báo mapper thành biến với kiểu `BiConsumer<T, Consumer<R>>`. Khi đó kiểu của phần tử nguồn và Consumer đầu ra đã được xác định trong khai báo biến:

```java
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

record Reading(String sensorId, double temperature) {}

List<Reading> readings = List.of(
    new Reading("S-01", 25.0),
    new Reading("S-02", 82.5)
);

BiConsumer<Reading, Consumer<String>> toAlerts =
    (reading, emit) -> {
        if (reading.temperature() >= 80.0) {
            emit.accept(reading.sensorId() + ": high temperature");
        }
    };

List<String> alerts = readings.stream()
    .mapMulti(toAlerts)
    .toList();
```

Ở đây, `Consumer<String>` trong kiểu của biến mapper đã xác định kiểu kết quả là `String`. Vì vậy, lời gọi `mapMulti(toAlerts)` không cần type witness bổ sung.

Cách này phù hợp khi mapper có logic dài, cần đặt tên hoặc được dùng lại ở nhiều pipeline. Với lambda ngắn chỉ sử dụng một lần, type witness trực tiếp thường gọn hơn.

## 9. Type witness không phải phép ép kiểu

Type witness và cast có mục đích khác nhau:

| Cách viết | Vai trò |
|---|---|
| `.<String>mapMulti(...)` | Chỉ định tham số kiểu `R` của generic method |
| `(String) value` | Ép kiểu một biểu thức; reference cast có thể được kiểm tra khi chạy |
| `Stream<String> result = ...` | Khai báo kiểu đích mà biểu thức cần đáp ứng |

Ví dụ type witness:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3);

Stream<String> labels = numbers.stream()
    .<String>mapMulti((number, emit) -> {
        emit.accept("N-" + number);
    });
```

Type witness làm cho tham số `emit` có kiểu `Consumer<String>`. Vì vậy, lời gọi `emit.accept` phải truyền vào giá trị tương thích với `String`.

Không nên cố giải quyết lỗi suy luận bằng cách ép kiểu cả Stream hoặc dùng raw type. Cách đó có thể che khuất lỗi kiểu và làm mất kiểm tra an toàn của generic. Hãy xác định kiểu đầu ra mong muốn và chỉ định nó trực tiếp ở lời gọi generic method.

Type witness cũng không chuyển đổi một đối tượng thành kiểu được chỉ định. Nếu phát một giá trị không tương thích với `R`, chương trình vẫn không biên dịch. Muốn chuyển đổi dữ liệu, hãy thực hiện chuyển đổi rõ ràng trước khi gọi `accept`.

## 10. Các biến thể mapMulti cho kiểu nguyên thủy

`mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble` có kiểu Stream kết quả cố định. Chúng sử dụng `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer`, vì vậy không có tham số kiểu đầu ra `R` để chỉ định bằng type witness như `mapMulti`.

Ví dụ:

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

`mapMultiToInt` trả về `IntStream`, nên không cần viết `.<Integer>mapMultiToInt`. Consumer trong lambda là `IntConsumer` và nhận giá trị `int`.

Hãy phân biệt `mapMulti` trả về `Stream<R>` với các biến thể chuyên biệt trả về primitive Stream. Chỉ phương thức generic có kiểu đầu ra `R` mới cần cân nhắc type witness cho kiểu kết quả.

## 11. Lỗi thường gặp khi dùng type witness

**Đặt type witness sau tên phương thức.** Cú pháp Java đúng là `stream.<String>mapMulti(...)`, không phải `stream.mapMulti<String>(...)`.

**Chọn kiểu R không tương thích với giá trị phát ra.** Nếu chỉ định `<String>`, mọi giá trị truyền vào Consumer phải tương thích với `String`. Nếu cần phát nhiều kiểu con, hãy chọn một kiểu cha hoặc interface phù hợp.

**Nghĩ rằng mọi lời gọi mapMulti đều cần type witness.** Trình biên dịch có thể suy luận được kiểu kết quả từ lambda và ngữ cảnh. Chỉ định tường minh khi cần làm rõ hoặc giải quyết lỗi suy luận.

**Dùng cast thay cho type witness.** Cast tác động lên một biểu thức; type witness xác định tham số kiểu của generic method. Hai cơ chế không thay thế nhau.

**Cho rằng var chỉ định kiểu kết quả.** `var` lấy kiểu từ biểu thức bên phải. Nếu muốn Stream có kiểu phần tử cụ thể, hãy dùng type witness hoặc một ngữ cảnh kiểu đích phù hợp.

**Nhầm type witness với chuyển đổi dữ liệu.** Type witness chỉ định kiểu ở thời điểm biên dịch. Hãy tự chuyển đổi giá trị trước khi phát nếu kiểu dữ liệu nguồn khác kiểu đầu ra mong muốn.

## 12. Ghi nhớ

- `mapMulti` có kiểu kết quả generic `R`, được phát qua `Consumer<R>`.
- Mapper trả về `void`, vì vậy suy luận kiểu kết quả đôi khi không rõ ràng như với `map`.
- Viết `.<String>mapMulti(...)` để chỉ định tường minh kiểu phần tử đầu ra.
- Type witness đặc biệt hữu ích khi kiểu `R` chưa rõ từ các nhánh phát kết quả, khi cần kiểu chung cho nhiều kiểu con hoặc khi không có ngữ cảnh kiểu đích rõ.
- Có thể khai báo mapper thành `BiConsumer<T, Consumer<R>>` để xác định kiểu bằng biến.
- Type witness là thông tin kiểu tại thời điểm biên dịch, không phải cast hay phép chuyển đổi dữ liệu.
- Các biến thể `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble` đã có kiểu đầu ra cố định nên không cần type witness cho `R`.

Khi hiểu vị trí và mục đích của type witness, ta có thể kiểm soát kiểu Stream kết quả ngay tại lời gọi `mapMulti`, giúp pipeline rõ ràng và dễ bảo trì hơn.

