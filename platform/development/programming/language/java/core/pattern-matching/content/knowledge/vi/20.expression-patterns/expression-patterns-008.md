# Pattern expression trong lambda

**Phạm vi:** Java Core Pattern Matching — Pattern trong biểu thức. Bài sử dụng cú pháp ổn định của **Java 21 trở lên**: type patterns trong `instanceof`, record patterns (JEP 440) và pattern matching for `switch` (JEP 441). Record pattern và pattern `switch` không cần `--enable-preview` kể từ Java 21.

## 1. Pattern expression trong lambda nghĩa là gì?

Một **lambda expression** cung cấp phần triển khai ngắn cho một functional interface, ví dụ `Predicate<T>` trả về `boolean` hoặc `Function<T, R>` nhận `T` và trả về `R`. Lambda có thể dùng một biểu thức làm thân hoặc một khối lệnh có `return`.

Một **pattern** mô tả điều kiện để một giá trị khớp kiểu/hình dạng và, nếu khớp, ràng buộc các biến. Java 21 cho phép dùng pattern trong những biểu thức như `instanceof` hoặc nhãn `case` của `switch`; các biểu thức đó có thể xuất hiện **ngay trong thân lambda**.

Ví dụ, record đại diện một tọa độ:

~~~java
record Point(int x, int y) {}
~~~

Từ danh sách các giá trị kiểu tổng quát, ta muốn chỉ giữ các Point thuộc góc phần tư thứ nhất:

~~~java
Predicate<Object> inFirstQuadrant = value ->
        value instanceof Point(int x, int y) && x > 0 && y > 0;
~~~

Ở đây lambda:

1. Nhận đối số `value` vì kiểu đích là `Predicate<Object>`.
2. Kiểm tra `value` có khớp record pattern `Point(int x, int y)` không.
3. Nếu khớp, lấy hai component vào các biến `x`, `y`.
4. Nhờ cơ chế **short-circuit** của `&&`, chỉ kiểm tra `x > 0 && y > 0` khi pattern đã khớp.
5. Trả về một `boolean` để `Predicate.test(value)` sử dụng.

**Pattern không thay thế lambda.** Lambda là cách truyền hành vi, còn pattern là cách kiểm tra và trích xuất dữ liệu *bên trong hành vi ấy*. Ta không tạo ra một loại “lambda pattern parameter” mới.

## 2. Ba cách phổ biến để dùng pattern trong thân lambda

### 2.1. Lambda có thân là một biểu thức `instanceof`

Khi chỉ cần trả về đúng/sai, dùng `Predicate` và biểu thức boolean:

~~~java
// Đoạn minh họa: Point là record được khai báo ở phần 1.
Predicate<Object> positivePoint = candidate ->
        candidate instanceof Point(int x, int y)
        && x > 0
        && y > 0;
~~~

Toàn bộ biểu thức sau dấu `->` là giá trị trả về của lambda. Không cần viết từ khóa `return`. Điều kiện `&&` diễn tả rõ quy tắc: đúng record Point, cả hai tọa độ dương.

Nếu chỉ kiểm tra kiểu, không cần lấy component, cũng có thể viết `candidate -> candidate instanceof Point`. Record pattern có ích khi cần sử dụng trực tiếp các component.

### 2.2. Lambda có thân là một khối lệnh

Khi cần nhiều bước xử lý hoặc thông báo lỗi riêng, dùng block lambda:

~~~java
Function<Object, String> describePoint = candidate -> {
    if (candidate instanceof Point(int x, int y)) {
        return "Point(" + x + "," + y + ")";
    }
    return "Not a Point";
};
~~~

Vì `Function<Object, String>` phải trả về `String`, mọi đường đi bình thường trong block phải có giá trị trả về. Biến pattern `x`, `y` chỉ khả dụng ở vùng code nơi việc khớp đã được chứng minh, như bên trong nhánh `if` ở ví dụ này.

### 2.3. Lambda có thân là `switch` expression

`switch` expression trả về một giá trị, nên có thể đặt sau dấu `->` của lambda:

~~~java
Function<Object, String> classify = value -> switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "origin";
    case Point(int x, int y) -> "point";
    case null -> "null";
    default -> "other";
};
~~~

Nhánh đầu có `when` chỉ khớp Point tại gốc tọa độ; nhánh Point thứ hai bao phủ các Point còn lại. Nhánh `null` và `default` xử lý những giá trị ngoài hai nhóm đó. Với selector là `Object`, các nhánh Point không bao phủ tất cả kiểu khác nên ví dụ cần một trường hợp dự phòng.

**Cẩn thận dấu chấm phẩy:** với `Function<...> f = value -> switch (value) { ... };`, dấu `;` cuối cùng kết thúc phép gán lambda. Mỗi nhánh `case ... ->` trong `switch` expression mang giá trị có kiểu tương thích với giá trị trả về của lambda.

## 3. Chương trình Java 21 hoàn chỉnh: Predicate, Function và Stream

Ví dụ dưới đây cho thấy pattern expression hoạt động trong lambda một cách thực tế, kể cả record lồng nhau, guard, null, stream filtering và `mapMulti`.

Lưu nguyên chương trình trong tệp **LambdaPatternDemo.java**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    public static void main(String[] args) {
        List<Object> values = List.of(
                new Point(2, 3),
                new Point(-1, 5),
                new Segment(new Point(1, 2), new Point(3, 4)),
                new Segment(new Point(0, 0), null),
                "other");

        Predicate<Object> positivePoint = value ->
                value instanceof Point(int x, int y) && x > 0 && y > 0;

        Function<Object, String> describe = value -> switch (value) {
            case Point(int x, int y) when x > 0 && y > 0 ->
                    "positive point: " + x + "," + y;
            case Point(int x, int y) ->
                    "point: " + x + "," + y;
            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "segment: " + x1 + "," + y1 + " -> " + x2 + "," + y2;
            case Segment(var start, var end) ->
                    "incomplete segment";
            case null -> "null value";
            default -> "unknown";
        };

        System.out.println(values.stream()
                .filter(positivePoint)
                .map(describe)
                .toList());

        values.forEach(value -> System.out.println(describe.apply(value)));
        System.out.println(describe.apply(null));

        List<Integer> totals = values.stream()
                .<Integer>mapMulti((value, downstream) -> {
                    if (value instanceof Point(int x, int y)) {
                        downstream.accept(x + y);
                    }
                })
                .toList();
        System.out.println(totals);
    }
}
~~~

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

~~~bash
javac LambdaPatternDemo.java
java LambdaPatternDemo
~~~

Đầu ra:

~~~text
[positive point: 2,3]
positive point: 2,3
point: -1,5
segment: 1,2 -> 3,4
incomplete segment
unknown
null value
[5, 4]
~~~

**Giải thích từng phần:**

- `positivePoint` là một lambda gắn với `Predicate<Object>`; nó chỉ trả về true cho `Point(2, 3)`. `Point(-1, 5)` không thỏa `x > 0`.
- `describe` là lambda trả về `String` bằng `switch` expression. Hai nhánh Point minh họa việc kết hợp record pattern với guard; nhánh có `when` đứng trước nhánh bao phủ mọi Point.
- `Segment(Point(...), Point(...))` yêu cầu **cả hai điểm** đều hiện diện. Segment có `end = null` không khớp nhánh lồng đó, nhưng khớp nhánh `Segment(var start, var end)`, nên nhận `incomplete segment`.
- `case null` cần được viết rõ nếu muốn xử lý selector null trong `switch` pattern matching; `default` xử lý các loại giá trị khác như `String`.
- `values.stream().filter(positivePoint).map(describe).toList()` dùng một lambda để lọc và một lambda để tạo mô tả; kết quả chỉ chứa phần tử Point có cả hai tọa độ dương.
- `mapMulti` đặt việc nhận dạng và trích tọa độ **trong cùng một lambda**. Chỉ các Point được chuyển thành tổng `x + y`, lần lượt là 5 và 4; các phần tử khác không phát giá trị nào.

Ví dụ dùng `List.of(...)` với các phần tử danh sách khác null; riêng selector null được kiểm tra qua `describe.apply(null)` vì **List.of không cho phép phần tử null**. Các component trong record vẫn có thể null nếu constructor cho phép, như `end` ở Segment thứ hai.

## 4. Flow scoping: vì sao dùng được biến pattern sau `&&`?

Java không cho phép tùy ý dùng biến khai báo trong pattern ở mọi chỗ. Trình biên dịch áp dụng **flow scoping**: biến chỉ khả dụng ở vùng mà đường thực thi chứng minh pattern đã khớp.

Biểu thức lambda sau là hợp lệ:

~~~java
Predicate<Object> rightHalf = value ->
        value instanceof Point(int x, int y) && x > 0;
~~~

Trong `A && B`, Java chỉ tính `B` nếu `A` true. Vì vậy khi đánh giá `x > 0`, mẫu `Point(int x, int y)` đã khớp và `x` tồn tại.

Ngược lại, đoạn sau **không biên dịch**:

~~~java
// SAI: khi vế trái false, x chưa được ràng buộc.
Predicate<Object> invalid = value ->
        value instanceof Point(int x, int y) || x > 0;
~~~

Với `A || B`, vế phải được tính khi vế trái false, nên `x` chưa chắc tồn tại. Không đổi `&&` thành `||` chỉ vì thấy chúng giống nhau về cú pháp; ý nghĩa điều kiện và phạm vi biến khác nhau.

Trong block lambda, nhánh `if` là một cách rõ ràng để kiểm soát phạm vi:

~~~java
Function<Object, Integer> sumIfPoint = value -> {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
};
~~~

Nếu nhánh từ chối kết thúc bằng `return`, biến pattern có thể khả dụng ở các dòng sau đó theo quy tắc flow scoping. Tuy nhiên một ví dụ sử dụng biến *chỉ bên trong nhánh khớp* thường dễ hiểu hơn cho người mới.

Biến `x` và `y` là biến cục bộ của mỗi lần thực thi lambda, không phải biến lưu trữ chung giữa các lượt gọi.

## 5. Pattern variable không đi qua ranh giới các lambda trong Stream

Điểm rất dễ nhầm: **biến pattern được khai báo bên trong một lambda không tự xuất hiện trong lambda tiếp theo**.

Ví dụ sau cố dùng `x` ở lambda của `map` và là **mã sai**:

~~~java
// SAI: x chỉ thuộc lambda bên trong filter.
values.stream()
        .filter(v -> v instanceof Point(int x, int y))
        .map(v -> x + y);
~~~

Trong pipeline, `filter` quyết định giữ hay bỏ **phần tử**, chứ không phát các biến pattern đã được ràng buộc. Lambda truyền vào `map` có phạm vi riêng; `x` không được khai báo tại đó.

Có ba cách xử lý hợp lý, tùy yêu cầu:

1. **Tách hành vi:** dùng `Predicate<Object>` để chọn đúng phần tử và `Function<Object, String>` để phân loại phần tử như chương trình chính. Mỗi lambda tự sử dụng pattern thích hợp trong phạm vi của mình.
2. **Giữ toàn bộ việc khớp và biến đổi trong một lambda:** dùng `mapMulti` khi muốn phát ra không hoặc một/vài kết quả cho mỗi phần tử. Ví dụ trong chương trình chính chỉ gọi `downstream.accept(x + y)` khi mẫu Point khớp.
3. **Đưa giá trị đã biến đổi ra khỏi lambda:** dùng `map` tạo object/record kết quả với dữ liệu đã cần dùng, rồi các bước sau xử lý object đó. Cách này phù hợp khi pipeline còn nhiều bước.

Không nên trông đợi cơ chế flow scoping kéo dài qua các đối số lambda độc lập. Thiết kế pipeline nên thể hiện rõ phần tử nào được truyền từ bước này sang bước tiếp theo.

## 6. Lambda parameter và pattern là hai khái niệm khác nhau

Khai báo một lambda đơn giản:

~~~java
Function<Object, String> label = candidate -> {
    if (candidate instanceof Point(int x, int y)) {
        return x + ":" + y;
    }
    return "other";
};
~~~

`candidate` là **tham số lambda**; `Point(int x, int y)` là **record pattern bên trong thân**.

Trong Java 21, không thể trực tiếp giải cấu trúc tham số lambda theo kiểu sau:

~~~java
// SAI: Java 21 không hỗ trợ record pattern làm formal parameter của lambda.
Function<Point, Integer> invalid = (Point(int x, int y)) -> x + y;
~~~

Cách đúng là nhận một tham số có kiểu thích hợp và dùng accessor hoặc kiểm tra pattern trong thân. Với `Function<Point, Integer>`, cách ngắn gọn nhất thường là:

~~~java
Function<Point, Integer> total = point -> point.x() + point.y();
~~~

Vì tham số đã được gõ kiểu Point, không phải lúc nào cũng cần pattern. **Pattern expression có giá trị nhất khi lambda nhận một kiểu tổng quát, một kiểu cha có nhiều biến thể hoặc một cấu trúc record cần phân tích.**

## 7. Kết hợp type pattern, record pattern và `switch` trong lambda

Các kiểu pattern hữu dụng ở những tình huống khác nhau:

| Trường hợp | Ví dụ trong thân lambda | Mục đích |
| --- | --- | --- |
| Chỉ cần nhận diện kiểu | `v instanceof Point` | Kiểm tra đối tượng thuộc kiểu Point |
| Cần giữ đối tượng sau kiểm tra | `v instanceof Point point` | Dùng chính object qua biến point |
| Cần hai component của record | `v instanceof Point(int x, int y)` | Lấy dữ liệu ngay tại điều kiện |
| Cần cấu trúc record lồng | `v instanceof Segment(Point(int x1, int y1), Point(int x2, int y2))` | Chỉ khớp khi hai component là Point |
| Cần nhiều nhánh trả về giá trị | `v -> switch (v) { ... }` | Dùng pattern trong các case của switch expression |
| Có thêm điều kiện sau khi khớp case | `case Point(int x, int y) when x > 0 -> ...` | Kết hợp matching với điều kiện phụ |

Trong `instanceof`, điều kiện thêm thường dùng `&&`. Từ khóa `when` là cú pháp **guard của case trong switch**, không phải toán tử tự do thay cho `&&` trong một biểu thức `instanceof`.

Với các kiểu sealed và `switch` exhaustive, lambda trả về kết quả từ một switch expression có thể không cần `default` khi các case bao phủ đầy đủ các subtype và selector. Với selector `Object` của ví dụ này, `default` cần thiết để xử lý những kiểu không thuộc Point hay Segment.

## 8. Null, thứ tự case và những điều kiện dễ sai

**Selector null trong `instanceof`:** biểu thức `value instanceof Point(int x, int y)` trả về false khi value là null. Các biến pattern không được ràng buộc.

**Record con null:** mẫu lồng `Segment(Point(...), Point(...))` sẽ không khớp nếu start hoặc end là null. Một mẫu `Segment(var start, var end)` vẫn có thể khớp Segment và ràng buộc giá trị null ở biến tham chiếu.

**Component lá null:** record pattern không mặc nhiên xác thực nội dung hoặc đảm bảo mọi thành phần tham chiếu khác null. Nếu dữ liệu có thể thiếu, dùng điều kiện rõ ràng trước khi gọi method trên nó.

**Thứ tự switch:** case rộng cho Point đặt trước case Point có guard có thể làm nhánh sau bị che khuất. Xếp nhánh có điều kiện cụ thể trước, rồi nhánh tổng quát.

**Phạm vi biến:** `x` trong một case không được dùng trong case khác nếu ở case đó chưa có ràng buộc tương ứng. Những biến cùng tên trong các nhánh độc lập không tự chia sẻ giá trị.

**Block lambda có kết quả:** với `Function`, đừng viết block chỉ có `if` trả về trong nhánh true rồi bỏ trống nhánh false; bảo đảm mọi đường đi bình thường trả đúng kiểu.

## 9. Về hiệu năng, side effects và lựa chọn cách viết

Pattern matching trong lambda không có phép màu về hiệu năng: nó giúp đưa điều kiện kiểu và dữ liệu cần dùng gần nơi xử lý. Trong stream, việc chạy qua bao nhiêu phần tử, có tạo object trung gian hay không và các phép tính bên trong mới quyết định phần lớn chi phí. Hãy đo bằng công cụ phù hợp nếu hiệu năng thật sự là yêu cầu.

Các lambda dùng trong `filter`, `map` nên dễ kiểm soát, tốt nhất hạn chế side effect khi không cần thiết. Biến bên ngoài mà lambda capture phải là **final** hoặc **effectively final**; biến pattern cục bộ trong lambda không bị ràng buộc bởi việc gán lại một biến capture bên ngoài.

Đừng lồng quá nhiều record patterns và guard trong một dòng chỉ để giảm số lệnh. Nếu dữ liệu sâu hoặc luật nghiệp vụ dài, hãy đưa logic vào một phương thức có tên:

~~~java
// Minh họa: giả định Point đã được khai báo.
static boolean isFirstQuadrant(Point point) {
    return point.x() > 0 && point.y() > 0;
}

// Lambda tập trung vào kiểu và gọi quy tắc có tên.
Predicate<Object> filter = value ->
        value instanceof Point point && isFirstQuadrant(point);
~~~

Khi đối tượng có nhiều nhánh xử lý phức tạp, cũng có thể tách `switch` expression thành một phương thức nhận kiểu đích rõ ràng rồi truyền method reference vào `map`. Mục tiêu là để mỗi lambda thể hiện một nhiệm vụ dễ nhận biết.

## 10. Lỗi phổ biến và checklist

Các lỗi hay gặp khi đưa pattern vào lambda gồm: khai báo record pattern trực tiếp ở formal parameter của lambda; dùng biến pattern bên phải `||` khi vế trái có thể false; tưởng biến tạo trong `filter` có hiệu lực ở `map`; dùng `when` ở ngoài `switch case`; đưa case tổng quát lên trước case có guard; quên selector null; trông đợi record con null khớp mẫu record lồng; hoặc quên `return` trên một đường đi của block lambda.

Trước khi chốt code, hãy tự kiểm tra:

- Kiểu đích của lambda (`Predicate`, `Function`, v.v.) có khớp tham số và giá trị trả về không?
- Pattern có thực sự được dùng trong **thân** lambda và có lợi hơn accessor đơn giản không?
- Mọi biến pattern chỉ được truy cập ở nơi compiler chứng minh việc khớp đã thành công không?
- Với `&&`, `||` và guard, các điều kiện ngắn mạch có đúng ý nghĩa không?
- Nếu dùng stream, phần tử truyền qua các bước và dữ liệu được trích xuất ở mỗi bước đã được phân biệt rõ chưa?
- Case của switch đã xét null, mẫu lồng không khớp và thứ tự ưu tiên chưa?
- Đã kiểm tra đầu vào hợp lệ, sai kiểu, giá trị biên và null chưa?

**Ghi nhớ:** lambda diễn tả hành động được truyền đi; pattern giúp hành động ấy kiểm tra **đúng loại dữ liệu** và lấy **đúng thành phần cần dùng**. Dùng `instanceof` cho predicate đơn giản, `switch` expression khi cần phân loại nhiều trường hợp, và giữ logic khớp cùng biến đổi trong một lambda khi cần dùng ngay các biến pattern.