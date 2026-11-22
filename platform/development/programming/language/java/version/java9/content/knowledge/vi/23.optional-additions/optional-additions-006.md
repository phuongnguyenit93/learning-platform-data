# stream() và ifPresentOrElse() trên OptionalInt, OptionalLong, OptionalDouble

Từ Java 9, ba kiểu Optional dành cho giá trị primitive là **OptionalInt**, **OptionalLong** và **OptionalDouble** có thêm hai phương thức hữu ích: **stream()** và **ifPresentOrElse()**. Một phương thức đưa giá trị tùy chọn vào primitive Stream để kết hợp với pipeline; phương thức còn lại xử lý riêng hai trường hợp có giá trị và rỗng.

Hai API này giúp viết mã rõ ràng khi làm việc với số nguyên, số nguyên dài và số thực, đồng thời giữ được các kiểu primitive chuyên biệt để tránh boxing không cần thiết.

## 1. Ba kiểu Optional primitive

Java cung cấp ba kiểu Optional chuyên biệt:

| Kiểu | Giá trị được chứa | Kiểu stream tương ứng | Consumer tương ứng |
|---|---|---|---|
| OptionalInt | int | IntStream | IntConsumer |
| OptionalLong | long | LongStream | LongConsumer |
| OptionalDouble | double | DoubleStream | DoubleConsumer |

Mỗi kiểu có thể ở một trong hai trạng thái:

- **Present:** đang chứa một giá trị primitive.
- **Empty:** không chứa giá trị.

Có thể tạo hai trạng thái bằng các factory method:

~~~java
OptionalInt present = OptionalInt.of(10);
OptionalInt empty = OptionalInt.empty();

OptionalLong longValue = OptionalLong.of(9_000_000_000L);
OptionalDouble decimalValue = OptionalDouble.of(3.14);
~~~

Các kiểu này được thiết kế để biểu diễn kết quả có thể không tồn tại mà không phải dùng null cho giá trị primitive. OptionalInt không phải Optional<Integer>; tương tự, OptionalLong và OptionalDouble không phải Optional<Long> và Optional<Double>.

## 2. stream(): chuyển Optional thành primitive Stream

Phương thức stream() được bổ sung vào OptionalInt, OptionalLong và OptionalDouble từ Java 9. Mỗi phương thức trả về primitive Stream tương ứng:

~~~java
IntStream intStream = OptionalInt.of(7).stream();
LongStream longStream = OptionalLong.of(12L).stream();
DoubleStream doubleStream = OptionalDouble.of(2.5).stream();
~~~

Quy tắc chuyển đổi:

- Nếu Optional có giá trị, stream() trả về Stream chứa đúng một phần tử.
- Nếu Optional rỗng, stream() trả về Stream rỗng, không có phần tử.

Ví dụ:

~~~java
OptionalInt.of(7).stream().forEach(System.out::println);
OptionalInt.empty().stream().forEach(System.out::println);
~~~

Chỉ dòng đầu in ra:

~~~text
7
~~~

Dòng thứ hai không in gì vì IntStream được tạo ra không có phần tử.

Ba kiểu trả về có thể dùng trực tiếp các thao tác của primitive Stream:

- IntStream hỗ trợ các thao tác như sum(), average(), min(), max(), summaryStatistics(), map() và filter().
- LongStream cung cấp các thao tác tương ứng cho long.
- DoubleStream cung cấp các thao tác tương ứng cho double.

Nhờ đó, giá trị vẫn được xử lý dưới dạng primitive thay vì phải chuyển thành Integer, Long hoặc Double để dùng Stream thông thường.

## 3. Kết hợp stream() với pipeline

Một lợi ích quan trọng của stream() là có thể đưa Optional primitive vào một pipeline đang xử lý dữ liệu.

Ví dụ, chuyển một OptionalInt thành IntStream rồi tính giá trị sau khi nhân đôi:

~~~java
int doubled = OptionalInt.of(21)
        .stream()
        .map(value -> value * 2)
        .sum();

System.out.println(doubled);
~~~

Kết quả:

~~~text
42
~~~

Nếu OptionalInt rỗng, IntStream không có phần tử nên sum() trả về giá trị identity của phép cộng là 0.

### Làm phẳng nhiều Optional primitive

Khi một collection chứa nhiều OptionalInt, OptionalLong hoặc OptionalDouble, có thể dùng flatMapToInt, flatMapToLong hoặc flatMapToDouble cùng method reference stream() để bỏ qua các phần tử rỗng và thu được một primitive Stream duy nhất.

~~~java
List<OptionalInt> optionalNumbers = List.of(
        OptionalInt.of(2),
        OptionalInt.empty(),
        OptionalInt.of(5)
);

int total = optionalNumbers.stream()
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(total);
~~~

Kết quả:

~~~text
7
~~~

Phần tử rỗng không tạo ra phần tử nào trong IntStream kết quả. Hai giá trị 2 và 5 được giữ lại, vì vậy tổng là 7.

Cách làm tương tự cho long và double:

~~~java
List<OptionalLong> optionalIds = List.of(
        OptionalLong.of(10L),
        OptionalLong.empty(),
        OptionalLong.of(20L)
);

long idTotal = optionalIds.stream()
        .flatMapToLong(OptionalLong::stream)
        .sum();

List<OptionalDouble> optionalScores = List.of(
        OptionalDouble.of(1.5),
        OptionalDouble.empty(),
        OptionalDouble.of(2.5)
);

double scoreTotal = optionalScores.stream()
        .flatMapToDouble(OptionalDouble::stream)
        .sum();
~~~

Các thao tác flatMapTo* phù hợp khi muốn loại bỏ trạng thái empty và tiếp tục xử lý các giá trị đang hiện diện trong một pipeline.

## 4. ifPresentOrElse(): xử lý riêng hai trạng thái

Phương thức ifPresentOrElse() cũng được bổ sung từ Java 9. Nó nhận hai hành động:

1. Hành động thứ nhất được chạy nếu Optional đang chứa giá trị.
2. Hành động thứ hai được chạy nếu Optional rỗng.

Chữ ký của ba kiểu:

~~~java
void ifPresentOrElse(IntConsumer action, Runnable emptyAction)
void ifPresentOrElse(LongConsumer action, Runnable emptyAction)
void ifPresentOrElse(DoubleConsumer action, Runnable emptyAction)
~~~

Ví dụ với OptionalInt:

~~~java
OptionalInt score = OptionalInt.of(85);
OptionalInt missingScore = OptionalInt.empty();

score.ifPresentOrElse(
        value -> System.out.println("Score: " + value),
        () -> System.out.println("No score")
);

missingScore.ifPresentOrElse(
        value -> System.out.println("Score: " + value),
        () -> System.out.println("No score")
);
~~~

Kết quả:

~~~text
Score: 85
No score
~~~

Với OptionalLong và OptionalDouble, cách sử dụng giống nhau nhưng lambda ở nhánh có giá trị nhận lần lượt long và double:

~~~java
OptionalLong accountId = OptionalLong.of(9_000_000_000L);

accountId.ifPresentOrElse(
        id -> System.out.println("Account: " + id),
        () -> System.out.println("No account")
);

OptionalDouble temperature = OptionalDouble.empty();

temperature.ifPresentOrElse(
        value -> System.out.println("Temperature: " + value),
        () -> System.out.println("No temperature")
);
~~~

Kết quả:

~~~text
Account: 9000000000
No temperature
~~~

Nhánh có giá trị nhận primitive thông qua IntConsumer, LongConsumer hoặc DoubleConsumer. Nhánh empty dùng Runnable vì không cần nhận đối số.

ifPresentOrElse() trả về void và thực thi hành động được chọn ngay trong lần gọi phương thức. Mỗi lần gọi chỉ chạy một trong hai nhánh. Đây là cách xử lý rõ ràng khi cần thực hiện hành động cho cả trường hợp có và không có dữ liệu.

## 5. So sánh stream() và ifPresentOrElse()

Hai phương thức cùng xử lý trạng thái present/empty nhưng phục vụ mục đích khác nhau:

| Tiêu chí | stream() | ifPresentOrElse() |
|---|---|---|
| Mục đích | Chuyển Optional thành primitive Stream | Thực thi một trong hai hành động |
| Khi có giá trị | Stream có một phần tử | Chạy action với giá trị primitive |
| Khi rỗng | Trả về Stream rỗng | Chạy emptyAction |
| Kiểu trả về | IntStream, LongStream hoặc DoubleStream | void |
| Cách sử dụng | Kết hợp map, filter, sum, flatMapTo* và các thao tác Stream | Xử lý trực tiếp trường hợp có hoặc không có giá trị |
| Thời điểm thực thi | Tạo Stream; các thao tác trung gian lazy cho đến terminal operation | Chạy nhánh tương ứng ngay khi gọi |

Ví dụ về khác biệt thời điểm:

~~~java
IntStream pipeline = OptionalInt.of(5)
        .stream()
        .map(value -> value * 2);

// Chưa có terminal operation nên pipeline chưa duyệt phần tử.
int result = pipeline.sum();

OptionalInt.of(5).ifPresentOrElse(
        value -> System.out.println("Present: " + value),
        () -> System.out.println("Empty")
);
~~~

Trong ví dụ này, pipeline của stream() chỉ thực hiện phép map khi sum() yêu cầu duyệt. Ngược lại, ifPresentOrElse() chạy action ngay khi được gọi.

Có thể chọn theo nhu cầu:

- Dùng stream() khi muốn kết hợp giá trị tùy chọn với các phép biến đổi, lọc, tổng hợp hoặc pipeline đang có.
- Dùng ifPresentOrElse() khi cần hai nhánh xử lý rõ ràng và không cần tạo Stream.

## 6. Ví dụ hoàn chỉnh cho cả ba kiểu

Lưu chương trình dưới tên **PrimitiveOptionalStreamDemo.java**. Ví dụ dùng các API có từ Java 9 và biên dịch được với Java 9 trở lên.

~~~java
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;

public class PrimitiveOptionalStreamDemo {
    public static void main(String[] args) {
        OptionalInt presentInt = OptionalInt.of(42);
        OptionalInt emptyInt = OptionalInt.empty();
        OptionalLong presentLong = OptionalLong.of(9_000_000_000L);
        OptionalLong emptyLong = OptionalLong.empty();
        OptionalDouble presentDouble = OptionalDouble.of(3.5);
        OptionalDouble emptyDouble = OptionalDouble.empty();

        presentInt.ifPresentOrElse(
                value -> System.out.println("int present: " + value),
                () -> System.out.println("int empty"));
        emptyInt.ifPresentOrElse(
                value -> System.out.println("unexpected int: " + value),
                () -> System.out.println("int empty"));

        presentLong.ifPresentOrElse(
                value -> System.out.println("long present: " + value),
                () -> System.out.println("long empty"));
        emptyLong.ifPresentOrElse(
                value -> System.out.println("unexpected long: " + value),
                () -> System.out.println("long empty"));

        presentDouble.ifPresentOrElse(
                value -> System.out.println("double present: " + value),
                () -> System.out.println("double empty"));
        emptyDouble.ifPresentOrElse(
                value -> System.out.println("unexpected double: " + value),
                () -> System.out.println("double empty"));

        int intSum = List.of(
                OptionalInt.of(2),
                OptionalInt.empty(),
                OptionalInt.of(5))
                .stream()
                .flatMapToInt(OptionalInt::stream)
                .sum();

        long longSum = List.of(
                OptionalLong.of(4_000_000_000L),
                OptionalLong.empty(),
                OptionalLong.of(6_000_000_000L))
                .stream()
                .flatMapToLong(OptionalLong::stream)
                .sum();

        double doubleSum = List.of(
                OptionalDouble.of(1.25),
                OptionalDouble.empty(),
                OptionalDouble.of(2.75))
                .stream()
                .flatMapToDouble(OptionalDouble::stream)
                .sum();

        long emptyStreamCount = OptionalDouble.empty().stream().count();

        System.out.println("int sum: " + intSum);
        System.out.println("long sum: " + longSum);
        System.out.println("double sum: " + doubleSum);
        System.out.println("empty double stream count: " + emptyStreamCount);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 PrimitiveOptionalStreamDemo.java
java PrimitiveOptionalStreamDemo
~~~

Kết quả stdout:

~~~text
int present: 42
int empty
long present: 9000000000
long empty
double present: 3.5
double empty
int sum: 7
long sum: 10000000000
double sum: 4.0
empty double stream count: 0
~~~

Ví dụ minh họa:

- Cả ba kiểu Optional đều xử lý được nhánh present và empty bằng ifPresentOrElse().
- Các method reference OptionalInt::stream, OptionalLong::stream và OptionalDouble::stream chuyển từng phần tử thành primitive Stream.
- flatMapToInt, flatMapToLong và flatMapToDouble làm phẳng các Stream con; Optional rỗng đóng góp 0 phần tử.
- count() trên Stream rỗng trả về 0.

## 7. Lưu ý khi sử dụng

- **Chọn đúng primitive type:** dùng OptionalInt cho int, OptionalLong cho long và OptionalDouble cho double để giữ đúng kiểu dữ liệu.
- **Tránh gọi getAsInt(), getAsLong() hoặc getAsDouble() khi chưa xác nhận có giá trị:** các phương thức này ném NoSuchElementException nếu Optional rỗng. Có thể dùng ifPresentOrElse() hoặc stream() tùy mục đích.
- **Không nhầm primitive Stream với Stream wrapper:** stream() của OptionalInt trả về IntStream, không phải Stream<Integer>. Tương tự với LongStream và DoubleStream.
- **Chú ý lazy evaluation:** stream() tạo nguồn Stream, nhưng các thao tác trung gian chỉ chạy khi có terminal operation.
- **Không tái sử dụng Stream đã tiêu thụ:** nếu cần xử lý lại, hãy tạo Stream mới từ Optional.
- **Giữ hành động đơn giản và rõ ràng:** action và emptyAction nên thể hiện đúng hai trường hợp dữ liệu để tránh logic khó theo dõi.

## 8. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng Stream<Integer> để nhận kết quả stream() của OptionalInt | Không đúng kiểu trả về | Dùng IntStream |
| Nghĩ stream() trả về một phần tử ngay cả khi Optional rỗng | Nhầm empty với giá trị mặc định | Stream rỗng có 0 phần tử; không tự sinh ra 0 |
| Chỉ xử lý action mà không xử lý empty | Bỏ qua trường hợp không có dữ liệu | Dùng ifPresentOrElse() khi cần hành động riêng cho trạng thái empty |
| Gọi getAsInt/getAsLong/getAsDouble mà không kiểm tra | Có thể ném NoSuchElementException | Xử lý trạng thái trước hoặc chuyển sang stream()/ifPresentOrElse() |
| Mong ifPresentOrElse() trả về giá trị | Nhầm phương thức hành động với phép biến đổi | Phương thức trả về void; dùng stream() nếu cần biến đổi và tổng hợp dữ liệu |
| Quên terminal operation sau khi tạo Stream | Pipeline chưa được thực thi | Gọi sum(), count(), forEach() hoặc terminal operation phù hợp |

## 9. Ghi nhớ

- stream() và ifPresentOrElse() được bổ sung cho OptionalInt, OptionalLong và OptionalDouble từ Java 9.
- stream() trả về IntStream, LongStream hoặc DoubleStream có 0 hoặc 1 phần tử.
- ifPresentOrElse() chạy action khi có giá trị và emptyAction khi Optional rỗng.
- Dùng flatMapToInt, flatMapToLong hoặc flatMapToDouble để kết hợp nhiều Optional primitive trong một pipeline.
- Stream hỗ trợ lazy evaluation; ifPresentOrElse() thực thi nhánh được chọn ngay khi gọi.
- Hai API này vẫn hữu ích trong Java hiện hành để xử lý dữ liệu primitive có thể vắng mặt mà không phải dùng raw type hoặc boxing không cần thiết.
