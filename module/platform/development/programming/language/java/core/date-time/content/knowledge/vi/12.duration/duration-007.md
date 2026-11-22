# Chuyển Duration sang mili giây hoặc nano giây và xử lý nguy cơ tràn số

## Mục tiêu

`java.time.Duration` biểu diễn một lượng thời gian theo giây và phần nano giây. Khi đổi sang mili giây hoặc nano giây bằng `toMillis()` và `toNanos()`, hai điều cần hiểu là **đơn vị nhỏ hơn có thể bị mất độ chính xác** và **kết quả có thể vượt giới hạn của kiểu `long`**.

Sau bài học, bạn sẽ biết chọn cách chuyển đổi, nhận diện phần bị cắt khi chuyển đơn vị, xử lý `ArithmeticException`, và tránh tự nhân/chia gây tràn số hoặc tính thời gian sai.

## 1. Duration lưu thời lượng như thế nào?

`Duration` không đại diện cho ngày giờ trên lịch hay múi giờ. Nó thể hiện độ dài thời gian, với độ phân giải nano giây. Về mặt mô hình, một giá trị có phần giây và nano giây chuẩn hóa; nano giây nằm trong khoảng từ 0 đến 999.999.999, ngay cả khi duration mang giá trị âm.

```java
Duration a = Duration.ofSeconds(2, 500_000_000);
Duration b = Duration.ofMillis(250);
Duration c = Duration.ofNanos(1_500);
```

Các giá trị tương ứng là 2,5 giây, 0,25 giây và 1.500 nano giây. `Duration` có thể rất dài; nó không bị giới hạn ở khoảng 24 giờ như nhiều kiểu chỉ dùng giờ, phút, giây trong ngày. Giá trị nội bộ có thể biểu diễn đến phạm vi rất rộng, nhưng chuyển nó thành một số `long` mili giây hoặc nano giây có thể không còn vừa.

Hai giới hạn cần ghi nhớ:

- `long` có giá trị lớn nhất là `Long.MAX_VALUE` (9.223.372.036.854.775.807), và nhỏ nhất là `Long.MIN_VALUE` (-9.223.372.036.854.775.808).
- Một giây có 1.000 mili giây và 1.000.000.000 nano giây. Vì vậy giới hạn số mili giây/nano giây tương ứng với các lượng thời gian khác nhau đáng kể.

## 2. Đổi Duration sang mili giây với toMillis()

Dùng `toMillis()` khi API đích nhận số mili giây, chẳng hạn timeout dạng millisecond, đo thời gian hiển thị hoặc giao tiếp với hệ thống cũ:

```java
Duration duration = Duration.ofSeconds(2, 345_678_900);

long millis = duration.toMillis();
System.out.println(millis);
```

Biên dịch phần ví dụ hoàn chỉnh ở mục 5 để chạy. Kết quả của phép chuyển là `2345`: phần 678.900 nano giây dưới một mili giây không được giữ trong giá trị `long` mili giây.

`toMillis()` chỉ trả về **một số nguyên**. Nó không thể mã hóa phần lẻ của mili giây. Nếu nghiệp vụ cần độ chính xác dưới mili giây, đừng chuyển sớm sang `long` mili giây.

## 3. Đổi Duration sang nano giây với toNanos()

Một nano giây bằng một phần tỷ giây. Dùng `toNanos()` khi API đích yêu cầu số nano giây và phạm vi giá trị chắc chắn vừa với `long`:

```java
Duration duration = Duration.ofMillis(1501);

long nanos = duration.toNanos();
System.out.println(nanos);
```

Kết quả là:

```text
1501000000
```

`toNanos()` cho phép biểu diễn chi tiết nhỏ hơn so với mili giây, nhưng cũng làm cho số nguyên tăng nhanh hơn. Giới hạn `long` ở đơn vị nano giây tương đương khoảng 292 năm mỗi chiều tính quanh không, trong khi phạm vi giây của `Duration` lớn hơn rất nhiều. Vì vậy một `Duration` có thể hoàn toàn hợp lệ nhưng `toNanos()` vẫn ném ngoại lệ.

## 4. Phần độ chính xác mất khi đổi đơn vị

Khi chuyển một duration sang đơn vị lớn hơn, các phần nhỏ hơn đơn vị đích không thể được giữ lại trong một số nguyên.

| Giá trị gốc | `toMillis()` | `toNanos()` | Ý nghĩa |
|---|---:|---:|---|
| `Duration.ofNanos(1)` | 0 | 1 | Một nano giây nhỏ hơn một mili giây. |
| `Duration.ofNanos(999_999)` | 0 | 999999 | Chưa đủ một mili giây. |
| `Duration.ofNanos(1_500_000)` | 1 | 1500000 | 0,5 mili giây bị bỏ ở kết quả mili giây. |
| `Duration.ofMillis(1501)` | 1501 | 1501000000 | Chuyển sang nano giây vẫn giữ nguyên lượng thời gian. |

Ví dụ: nếu thời lượng là 1,999 mili giây, kết quả `toMillis()` là 1 millisecond nguyên; phần 0,999 mili giây không xuất hiện trong kết quả. Java không tự làm tròn lên theo kiểu “gần nhất” chỉ vì phần lẻ lớn. Nếu cần làm tròn cho nghiệp vụ (chẳng hạn không bao giờ đặt timeout ngắn hơn thời lượng yêu cầu), hãy định nghĩa chính sách làm tròn rõ ràng thay vì giả định `toMillis()` làm việc đó.

`toMillisPart()`, `toSecondsPart()` và các phương thức `*Part()` khác có thể lấy thành phần để hiển thị; chúng không thay thế phép tính tổng thời gian và không tự giải quyết bài toán làm tròn.

### Đừng nhầm với phép chuyển của TimeUnit

`TimeUnit.NANOSECONDS.toMillis(value)` làm việc với một giá trị `long` đã ở đơn vị nano giây và cắt phần lẻ. Cách chuyển của `TimeUnit` có quy tắc xử lý overflow khác: chuyển đổi thời gian quá lớn được bão hòa ở giới hạn `long` thay vì ném `ArithmeticException` trong những phép chuyển đó. `Duration.toMillis()` và `Duration.toNanos()` ném `ArithmeticException` khi kết quả không biểu diễn được. Không thay API này bằng API kia nếu hệ thống phụ thuộc hành vi overflow.

## 5. Ví dụ hoàn chỉnh: hai đơn vị và phần bị mất

Tạo tệp `DurationUnitConversionDemo.java`:

```java
import java.time.Duration;

public class DurationUnitConversionDemo {
    public static void main(String[] args) {
        Duration duration = Duration.ofSeconds(2, 345_678_900);

        System.out.println("Duration: " + duration);
        System.out.println("Millis:   " + duration.toMillis());
        System.out.println("Nanos:    "
                + Duration.ofMillis(1501).toNanos());
        System.out.println("Sub-ms:   " + Duration.ofNanos(999_999).toMillis());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac DurationUnitConversionDemo.java
java DurationUnitConversionDemo
```

Đầu ra:

```text
Duration: PT2.3456789S
Millis:   2345
Nanos:    1501000000
Sub-ms:   0
```

Các kết quả cho thấy `toMillis()` bỏ phần chưa đủ một mili giây; chuyển duration 1501 mili giây sang nano giây thì cho tổng nano giây tương ứng. Mỗi số kết quả chỉ an toàn khi chuyển đổi không vượt phạm vi `long`.

## 6. Vì sao có thể tràn số?

Một lỗi phổ biến là lấy tổng giây rồi nhân với 1.000 hoặc 1.000.000.000:

```java
long millis = duration.getSeconds() * 1000;
long nanos = duration.getSeconds() * 1_000_000_000;
```

Phép nhân số nguyên của Java có thể tràn mà không tự ném ngoại lệ; kết quả khi đó sai và có thể mang dấu ngược dự định. Đoạn trên còn bỏ qua phần nano giây của duration, nên không phải cách chuyển đổi đầy đủ kể cả khi phép nhân vừa phạm vi.

Hãy ưu tiên `duration.toMillis()` và `duration.toNanos()`: chúng đã xử lý phần nano giây và dùng phép toán kiểm tra tràn số. Nếu kết quả không vừa `long`, chúng ném `ArithmeticException` thay vì trả một số bị cuộn vòng.

Một `Duration` rất dài vẫn có thể được tạo thành công:

```java
Duration huge = Duration.ofSeconds(Long.MAX_VALUE);
```

Nhưng `huge.toMillis()` không thể thành công vì cần nhân số giây cực lớn với 1.000 để tạo tổng mili giây. Tương tự, ngay cả các duration ngắn hơn nhiều cũng có thể vượt giới hạn nano giây vì hệ số chuyển là một tỷ.

## 7. Bắt ArithmeticException tại ranh giới chuyển đổi

Nếu dữ liệu bên ngoài có thể yêu cầu thời lượng lớn không giới hạn, xử lý lỗi ngay tại nơi chuyển sang `long`:

```java
import java.time.Duration;

public class DurationOverflowDemo {
    public static void main(String[] args) {
        Duration huge = Duration.ofSeconds(Long.MAX_VALUE);

        try {
            long millis = huge.toMillis();
            System.out.println("Millis: " + millis);
        } catch (ArithmeticException ex) {
            System.out.println("Milliseconds out of long range");
        }

        try {
            long nanos = huge.toNanos();
            System.out.println("Nanos: " + nanos);
        } catch (ArithmeticException ex) {
            System.out.println("Nanoseconds out of long range");
        }
    }
}
```

```bash
javac DurationOverflowDemo.java
java DurationOverflowDemo
```

Đầu ra:

```text
Milliseconds out of long range
Nanoseconds out of long range
```

Đoạn mã không in thông điệp ngoại lệ của JVM vì chi tiết thông điệp có thể phụ thuộc chỗ phát sinh. Nó xử lý loại ngoại lệ và in ra thông điệp nghiệp vụ ổn định.

Không nên bắt `Exception` chung chung nếu mục tiêu là xử lý overflow của phép đổi đơn vị. Bắt đúng `ArithmeticException` giúp phân biệt trường hợp vượt phạm vi số với những lỗi khác của chương trình.

## 8. Chọn cách xử lý overflow theo hợp đồng nghiệp vụ

Bắt được overflow chỉ là bước đầu. Ứng dụng cần quyết định nếu độ dài không thể biểu diễn bằng đơn vị/API đích thì phải làm gì.

- **Từ chối đầu vào:** thích hợp khi thời lượng vượt giới hạn là dữ liệu không hợp lệ. Báo lỗi ở ranh giới nhập liệu hoặc API, và không tiếp tục như thể conversion thành công.
- **Đặt giới hạn rõ ràng:** phù hợp cho timeout, retry hoặc khoảng chờ. Kiểm tra theo giới hạn do hệ thống quy định trước khi truyền cho thư viện.
- **Bão hòa về giới hạn:** chỉ dùng khi hợp đồng nói rõ mọi giá trị vượt mức sẽ được hiểu là mức tối đa/tối thiểu. Hãy trả về `Long.MAX_VALUE` hoặc `Long.MIN_VALUE` một cách tường minh; đừng nhầm đây là hành vi của `Duration.toMillis()`.
- **Giữ Duration:** nếu thành phần tiếp theo cũng nhận `Duration`, đừng chuyển sang `long` sớm. Giữ kiểu giàu ý nghĩa giúp tránh mất độ chính xác và trì hoãn quyết định về giới hạn tới ranh giới cần số nguyên.

Nếu phải kiểm tra biên, nên dùng API có kiểm tra overflow để chuyển đổi và xử lý ngoại lệ, hoặc viết phép kiểm tra bằng giới hạn đã xác minh. Tránh tự nhân trước rồi mới kiểm tra vì giá trị đã có thể bị tràn.

## 9. Các chiến lược thường gây lỗi

### 9.1. Tự nhân giây

```java
long nanos = duration.getSeconds() * 1_000_000_000;
```

Có hai vấn đề: phép nhân có thể tràn lặng lẽ, và phần nano giây dư trong `Duration` bị bỏ. Dùng `toNanos()` và xử lý `ArithmeticException`.

### 9.2. Cho rằng Duration không thể tràn

`Duration` có thể chứa giá trị giây lớn, không có nghĩa tổng số nano giây của nó cũng vừa `long`. Luôn phân biệt phạm vi của kiểu nguồn với phạm vi của đơn vị đích.

### 9.3. Mặc định làm tròn lên hoặc xuống

`toMillis()` trả về mili giây nguyên, không có tham số làm tròn nghiệp vụ. Với timeout dương, nếu yêu cầu là đảm bảo thời gian chờ không ngắn hơn yêu cầu gốc, cách cắt phần lẻ có thể không đạt yêu cầu. Hãy xác định rõ “cắt”, “làm tròn lên” hay một quy tắc khác và kiểm tra overflow cả trong phép tính làm tròn.

### 9.4. Dùng TimeUnit mà không xét khác biệt

`TimeUnit` và `Duration` có API, đầu vào và chính sách overflow khác nhau. Nếu code cần nhận biết thời lượng không thể chuyển được, dùng phương thức `Duration` có kiểm tra và xử lý ngoại lệ. Chỉ dùng chuyển đổi bão hòa khi đó thực sự là hợp đồng mong muốn.

### 9.5. Bỏ qua phần nano giây khi đọc thủ công

`getSeconds()` là thành phần giây chuẩn hóa, không phải tổng giây làm tròn. Nếu cần quy đổi toàn bộ duration, phải tính cả phần nano giây và xử lý tràn chính xác; thông thường nên dùng API chuyển đổi có sẵn.

## 10. Các phương thức liên quan

| API | Trả về | Dùng khi |
|---|---|---|
| `toMillis()` | Tổng mili giây dạng `long` | API nhận tổng mili giây và giá trị nằm trong phạm vi. |
| `toNanos()` | Tổng nano giây dạng `long` | Cần độ chi tiết nano giây và giá trị nằm trong phạm vi. |
| `toDays()`, `toHours()`, `toMinutes()`, `toSeconds()` | Tổng đơn vị nguyên dạng `long` | Cần tổng theo đơn vị tương ứng, chấp nhận bỏ phần nhỏ hơn đơn vị. |
| `toMillisPart()` | Thành phần mili giây trong giây | Hiển thị thành phần; không phải tổng mili giây. |
| `toNanosPart()` | Thành phần nano giây đã chuẩn hóa | Hiển thị/tính toán thành phần; không phải tổng nano giây. |
| `getSeconds()`, `getNano()` | Thành phần giây và nano giây chuẩn hóa | Khi thực sự cần truy cập cấu trúc nội bộ; phải tự quản lý phép tính và overflow nếu chuyển đổi thủ công. |

Khi cần chuỗi dễ đọc, `Duration.toString()` cho dạng như `PT2.3456789S`; đây là định dạng ISO-8601 về thời lượng. Khi cần tính tổng theo một đơn vị, dùng `toMillis()` hoặc `toNanos()`, không parse chuỗi `toString()` để làm số học.

## 11. Tự kiểm tra

**Câu 1.** `Duration.ofNanos(999_999).toMillis()` trả về bao nhiêu?

**Đáp án:** `0`, vì duration chưa đủ một mili giây. Phần lẻ bị mất khi trả về số nguyên mili giây.

**Câu 2.** Vì sao `Duration.ofSeconds(Long.MAX_VALUE)` tạo được đối tượng nhưng `toMillis()` có thể ném ngoại lệ?

**Đáp án:** Kiểu `Duration` biểu diễn giây trong miền lớn hơn phạm vi tổng mili giây của `long`; phép nhân khi quy đổi không vừa `long` và ném `ArithmeticException`.

**Câu 3.** Có nên tự dùng `duration.getSeconds() * 1000` để thay `toMillis()` không?

**Đáp án:** Không. Phép nhân có thể tràn âm thầm và bỏ qua phần nano giây. `toMillis()` vừa tính cả phần lẻ theo quy tắc API vừa kiểm tra overflow.

**Câu 4.** Khi hệ thống muốn từ chối thời lượng không chuyển được sang nano giây, nên xử lý ở đâu?

**Đáp án:** Bao quanh `toNanos()` bằng xử lý `ArithmeticException` tại ranh giới chuyển đổi, sau đó trả lỗi hoặc từ chối dữ liệu theo hợp đồng API.

**Câu 5.** `toMillisPart()` có phải tổng số mili giây của duration không?

**Đáp án:** Không. Nó là thành phần mili giây, nên với duration dài hơn một giây nó không thể thay thế `toMillis()`.

---

**Quy tắc thực hành:** Giữ `Duration` cho đến ranh giới thực sự cần số nguyên. Dùng `toMillis()` hoặc `toNanos()` để chuyển đổi có kiểm tra; khi gặp `ArithmeticException`, áp dụng chính sách nghiệp vụ rõ ràng thay vì để phép nhân bị tràn và tạo ra kết quả sai.