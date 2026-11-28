# Pattern nguyên thủy trong record pattern

Record pattern cho phép kiểm tra một giá trị có thuộc một record hay không và lấy các component của record ngay trong biểu thức khớp mẫu. Từ Java 21, record pattern là tính năng chính thức. Java 26 mở rộng khả năng này bằng **primitive type pattern** trong component list, cho phép kiểm tra và chuyển đổi an toàn một component có kiểu nguyên thủy sang kiểu nguyên thủy khác.

Tuy nhiên, primitive patterns không phải tính năng ổn định của Java 26. Chúng là preview lần thứ tư qua JEP 530. JDK 27 tiếp tục preview lần thứ năm, nhưng ngày 09/11/2026 nhóm phát triển Project Amber thông báo dừng phát triển và quyết định loại tính năng khỏi JDK 28. Vì vậy, nội dung này hữu ích để hiểu và đọc mã thử nghiệm trên JDK 26/27; không nên chọn primitive patterns làm nền tảng cho mã production cần nâng cấp qua các bản JDK tiếp theo.

## 1. Record pattern và component pattern

Một record pattern có tên record và danh sách pattern tương ứng với các component đã khai báo. Khi khớp, Java kiểm tra kiểu record, gọi accessor của từng component và tiếp tục kiểm tra pattern tương ứng.

```java
record Point(double x, double y) {}

static void printPoint(Object value) {
    if (value instanceof Point(var x, var y)) {
        System.out.println("x = " + x + ", y = " + y);
    }
}
```

`Point(var x, var y)` vừa kiểm tra `value` là một `Point`, vừa lấy hai giá trị component vào biến pattern `x` và `y`. `var` suy luận kiểu `double` từ các component. Không cần gọi thủ công `point.x()` và `point.y()` sau khi đã khớp.

Record pattern cơ bản là tính năng chính thức từ Java 21 (JEP 440), và `var` có thể lấy component nguyên thủy mà không cần preview. Cú pháp tường minh như `Point(double x, double y)` dùng primitive type pattern, nên vẫn cần preview trong JDK 26. Primitive pattern mở rộng cách viết này: kiểu khai báo biến pattern có thể khác kiểu component, miễn phép chuyển đổi giá trị tại thời điểm chạy là chính xác.

## 2. Khớp component nguyên thủy với kiểu nguyên thủy khác

Ví dụ điển hình trong tài liệu Java 26:

```java
public class PrimitiveRecordPatternDemo {
    record Cup(double d) {}

    static void inspect(Object value) {
        if (value instanceof Cup(double d)) {
            System.out.println("Cup contains double: " + d);
        }
        if (value instanceof Cup(float f)) {
            System.out.println("Cup contains float: " + f);
        }
        if (value instanceof Cup(int i)) {
            System.out.println("Cup contains int: " + i);
        }
    }

    public static void main(String[] args) {
        Cup cup = new Cup(34.567f);
        inspect(cup);
    }
}
```

Kết quả tương tự:

```text
Cup contains double: 34.56700134277344
Cup contains float: 34.567
```

Không có dòng `Cup contains int`. Lý do:

- `Cup(double d)` khớp vì component có kiểu `double`.
- `Cup(float f)` khớp vì giá trị `double` trong record chính là giá trị `float` ban đầu đã được mở rộng sang `double`; chuyển ngược về `float` không làm mất thông tin.
- `Cup(int i)` không khớp vì giá trị có phần thập phân. Chuyển sang `int` sẽ làm mất phần thông tin này.

Con số `34.56700134277344` là biểu diễn `double` chính xác của giá trị gần đúng đã được lưu ở dạng `float` khi truyền `34.567f` vào constructor. Pattern `float f` lấy lại đúng giá trị `float` ban đầu. Nếu khởi tạo bằng `new Cup(34.567)` (literal kiểu `double`), pattern `Cup(float f)` không khớp vì chuyển giá trị đó sang `float` sẽ mất độ chính xác.

## 3. Quy tắc chuyển đổi chính xác

Primitive pattern không thực hiện một phép ép kiểu có thể làm mất dữ liệu rồi vẫn xem là khớp. Java chỉ xem component khớp khi phép chuyển đổi kiểm tra (*testing conversion*) sang kiểu trong pattern là **exact**: phép chuyển đổi không làm mất thông tin và không ném ngoại lệ.

Tính chính xác được đánh giá theo giá trị thực tế, không chỉ theo cặp kiểu. Một số trường hợp:

| Kiểu component | Primitive pattern | Khi nào có thể khớp? |
|---|---|---|
| `double` | `double d` | Luôn khớp với component hợp lệ kiểu `double` |
| `double` | `float f` | Chỉ khi chuyển từ giá trị `double` sang `float` không mất thông tin |
| `double` | `int i` | Chỉ khi giá trị là số nguyên nằm trong miền `int` và chuyển đổi không mất thông tin |
| `int` | `long n` | Có thể khớp vì mở rộng `int` sang `long` là chính xác |
| `int` | `byte b` | Chỉ khi giá trị component nằm trong miền `byte` |

Ví dụ với narrowing conversion:

```java
record Reading(int value) {}

static void inspectReading(Reading reading) {
    if (reading instanceof Reading(byte value)) {
        System.out.println("Có thể biểu diễn chính xác bằng byte: " + value);
    } else {
        System.out.println("Giá trị không thể biểu diễn chính xác bằng byte");
    }
}
```

`new Reading(100)` có thể khớp với `Reading(byte value)`, còn `new Reading(200)` thì không vì 200 nằm ngoài miền của `byte`. Pattern không âm thầm cắt bớt bit như một phép ép kiểu `(byte) 200`.

Đối với số thực, phép chuyển đổi có thể mất độ chính xác hoặc miền biểu diễn. Chẳng hạn, `double` sang `float` có thể làm tròn, tràn thành vô cực hoặc biến một giá trị khác 0 thành 0. Những trường hợp như vậy không được xem là khớp nếu chuyển đổi không exact. Với số nguyên, chuyển đổi thu hẹp có thể làm thay đổi độ lớn hoặc dấu; pattern chỉ khớp nếu giá trị cụ thể vẫn được bảo toàn.

Không nên hiểu quy tắc này là Java chỉ cho phép widening conversion. Một narrowing conversion vẫn có thể khớp nếu giá trị cụ thể nằm trong miền đích và không mất thông tin. Ngược lại, ngay cả một số widening conversion cũng có thể mất độ chính xác, ví dụ `int` sang `float` với số nguyên đủ lớn.

## 4. `var` khác với primitive type pattern

Trong record pattern, `var` yêu cầu trình biên dịch suy luận kiểu component. Nó không kiểm tra xem giá trị có thể biểu diễn chính xác bằng một kiểu nguyên thủy khác hay không.

```java
record Cup(double d) {}

static void printCup(Object value) {
    if (value instanceof Cup(var amount)) {
        // amount có kiểu double vì component d có kiểu double.
        System.out.println(amount);
    }
}
```

So sánh:

- `Cup(var amount)` suy luận `amount` là `double`, theo kiểu khai báo của component.
- `Cup(float amount)` yêu cầu component `double` có thể chuyển chính xác thành `float`; nếu không thì toàn bộ record pattern không khớp.

Dùng `var` khi chỉ cần lấy giá trị component với kiểu tự nhiên của nó. Dùng primitive type pattern khi mục tiêu thực sự là kiểm tra khả năng biểu diễn chính xác bằng một kiểu nguyên thủy khác.

## 5. Kết hợp với nested record pattern

Primitive pattern có thể nằm sâu bên trong record pattern lồng nhau. Điều này giúp kiểm tra cấu trúc dữ liệu và điều kiện biểu diễn số trong cùng một biểu thức.

```java
record Coordinate(double latitude, double longitude) {}
record SensorReading(String sensorId, Coordinate location, double value) {}

static void inspect(Object input) {
    if (input instanceof SensorReading(
            String id,
            Coordinate(double latitude, double longitude),
            float value)) {
        System.out.printf(
                "%s: (%f, %f), reading as float = %f%n",
                id, latitude, longitude, value);
    }
}
```

Pattern chỉ khớp khi:

1. `input` là một `SensorReading`.
2. Component `sensorId` khớp với `String id`.
3. Component `location` khớp với record `Coordinate`, rồi hai component tọa độ khớp với `double`.
4. Component `value` có thể chuyển chính xác từ `double` sang `float`.

Giá trị `null` không khớp với record pattern ở cấp ngoài. Nếu một component tham chiếu dùng nested record pattern hoặc type pattern cần một đối tượng cụ thể, component `null` cũng không thỏa pattern đó. Accessor của record được gọi trong quá trình deconstruct; nếu accessor kết thúc bất thường, quá trình pattern matching có thể ném `MatchException` với nguyên nhân tương ứng.

## 6. Dùng trong `switch` và thứ tự pattern

Record pattern là thành phần của pattern matching trong `switch`. Khi primitive patterns được bật preview, component pattern cũng có thể kiểm tra chuyển đổi nguyên thủy trong từng nhánh.

```java
record Cup(double d) {}

static String describe(Cup cup) {
    return switch (cup) {
        case Cup(float f) when f > 0 ->
                "Giá trị biểu diễn chính xác bằng float và dương: " + f;
        case Cup(double d) ->
                "Giữ giá trị double: " + d;
    };
}
```

Nhánh `Cup(float f)` chỉ khớp với tập con giá trị `double` có thể chuyển chính xác sang `float` và thỏa điều kiện `f > 0`. Nhánh `Cup(double d)` xử lý các giá trị còn lại. Pattern bao phủ mọi giá trị của component `double` phải đặt sau pattern hẹp hơn; nếu một pattern bao phủ đã xuất hiện trước, pattern phía sau có thể bị kiểm tra dominance và bị báo lỗi biên dịch.

JDK 26 (JEP 530) điều chỉnh định nghĩa *unconditional exactness* và siết kiểm tra dominance trong `switch`. Vì vậy, khi chuyển mã thử nghiệm từ JDK 25 sang JDK 26, cần biên dịch lại thay vì cho rằng mọi thứ tự `case` cũ vẫn được chấp nhận.

## 7. Trạng thái preview và quyết định rút tính năng

Cần phân biệt trạng thái của hai phần:

- **Record patterns cơ bản:** chính thức từ Java 21, không cần `--enable-preview`.
- **Primitive type patterns bên trong record patterns:** preview trong JDK 26 theo JEP 530 (lần thứ tư); tiếp tục preview trong JDK 27 theo JEP 532 (lần thứ năm). Đây chưa phải cú pháp ổn định của Java SE.

Nếu chỉ muốn thử nghiệm cú pháp trên JDK 26, bật preview khi biên dịch và chạy bằng đúng JDK 26:

```bash
javac --release 26 --enable-preview -d out src/PrimitiveRecordPatternDemo.java
java --enable-preview -cp out PrimitiveRecordPatternDemo
```

Với JDK 27, dùng JDK 27 ở cả hai bước và thay mức phát hành bằng 27:

```bash
javac --release 27 --enable-preview -d out src/PrimitiveRecordPatternDemo.java
java --enable-preview -cp out PrimitiveRecordPatternDemo
```

Preview được ràng buộc với bản phát hành tương ứng. Không biên dịch bằng preview của một JDK rồi kỳ vọng chạy lớp đó như tính năng chính thức trên JDK khác. Mỗi lần nâng JDK cần biên dịch lại và kiểm tra lại mã nguồn.

**Cập nhật quan trọng tại ngày 27/11/2026:** thông báo trên mailing list `amber-spec-experts` ngày 09/11/2026 cho biết nhóm phát triển quyết định dừng phát triển Primitive Types in Patterns, `instanceof`, and `switch`; draft JEP cho preview lần thứ sáu sẽ được rút và tính năng sẽ bị loại khỏi JDK 28. Lý do là thiết kế hiện tại dựa trên quy tắc exact numeric conversion, trong khi Project Valhalla vẫn đang phát triển hướng đi mới cho kiểu số, có thể gồm kiểu số do người dùng định nghĩa. Việc chuẩn hóa quy tắc chuyển đổi ở thời điểm này có thể quá sớm.

Thông báo cũng đề cập hướng thiết kế Constant Patterns đang được chuẩn bị để hỗ trợ một số trường hợp dùng hằng trong `switch` và lồng trong record pattern, ví dụ `case Point(0, 0)`. Đây là hướng phát triển khác, không đồng nghĩa primitive type patterns đã trở thành tính năng ổn định hay có thể thay thế trực tiếp mọi trường hợp sử dụng.

## 8. Cách viết tương thích lâu dài

Với mã production cần chạy trên các JDK tiếp theo, dùng record pattern cơ bản đã ổn định để lấy component, sau đó thực hiện chuyển đổi và kiểm tra điều kiện một cách tường minh. Ví dụ sau chỉ chấp nhận giá trị hữu hạn có thể biểu diễn chính xác bằng `float`:

```java
record Cup(double d) {}

static void inspectStable(Object value) {
    if (value instanceof Cup cup) {
        double d = cup.d();
        float f = (float) d;

        if (Double.isFinite(d) && (double) f == d) {
            System.out.println("Exact float value: " + f);
        } else {
            System.out.println("Keep the double value: " + d);
        }
    }
}
```

Nếu cần chuyển `double` sang `int`, kiểm tra tính hữu hạn, miền giá trị và phần thập phân trước khi ép kiểu:

```java
static boolean fitsExactlyInInt(double value) {
    return Double.isFinite(value)
            && value >= Integer.MIN_VALUE
            && value <= Integer.MAX_VALUE
            && value == Math.rint(value);
}
```

Kiểu kiểm tra cụ thể phải phù hợp với miền dữ liệu của ứng dụng. Ví dụ trên chủ động loại NaN và vô cực vì chỉ chấp nhận số hữu hạn; nếu nghiệp vụ có quy tắc khác, hãy định nghĩa rõ quy tắc đó. Không thay một phép kiểm tra exact bằng phép ép kiểu thu hẹp đơn thuần.

## 9. Những điểm cần nhớ

- Record pattern cơ bản là tính năng chính thức từ Java 21; primitive type pattern bên trong component list vẫn là preview ở JDK 26 và JDK 27.
- Primitive pattern có thể yêu cầu chuyển component sang kiểu nguyên thủy khác, nhưng chỉ khớp nếu phép chuyển đổi tại runtime là exact.
- Narrowing conversion không tự động bị cấm; nó chỉ khớp với giá trị cụ thể nếu không mất thông tin.
- `var` suy luận kiểu component, không kiểm tra khả năng biểu diễn bằng kiểu nguyên thủy khác.
- `null` không khớp record pattern; nested pattern còn phải thỏa điều kiện của từng component.
- Theo thông báo ngày 09/11/2026, Primitive Patterns sẽ bị loại khỏi JDK 28. Không dùng cú pháp preview này làm nền tảng cho mã cần duy trì lâu dài.
- Với mã production, dùng record pattern ổn định để lấy component và kiểm tra miền/độ chính xác bằng logic tường minh.

## Tài liệu tham khảo

- [Java SE 26 Language Guide: Record Patterns](https://docs.oracle.com/en/java/javase/26/language/record-patterns.html)
- [Java SE 26 JLS: Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Java Language Changes by Release — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html)
- [JEP 530: Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
- [JDK 27 Release Notes — Primitive Types in Patterns (Fifth Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JEP 532: Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532)
- [OpenJDK Amber Spec Experts: Withdrawing the Primitive Patterns preview feature, 09/11/2026](https://www.mail-archive.com/amber-spec-experts%40openjdk.org/msg00923.html)
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440)
- [JEP 12: Preview Features](https://openjdk.org/jeps/12)
