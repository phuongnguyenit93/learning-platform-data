# Tràn số nguyên và sai số số thực trong Reduction

**Chủ đề:** Java 8 → Reduction → Tràn số nguyên và sai số số thực.

Trong Java Stream, **reduction** gộp nhiều phần tử thành một kết quả, ví dụ tổng, tích, trung bình hoặc giá trị lớn nhất. Một phép tính nhìn có vẻ đúng về mặt toán học có thể cho kết quả sai khi biểu diễn bằng **int**, **long**, **float** hoặc **double**. Hai nhóm vấn đề khác nhau phải nhận diện là:

- **Tràn số nguyên (integer overflow):** giá trị toán học vượt phạm vi mà kiểu nguyên cố định biểu diễn được; phép cộng/nhân nguyên thông thường không tự phát lỗi và có thể quay vòng sang giá trị khác.
- **Sai số số thực (floating-point rounding error):** một số thập phân hoặc kết quả trung gian không biểu diễn chính xác trong hệ nhị phân, nên phép tính làm tròn và thứ tự tính ảnh hưởng kết quả.

Đây vẫn là các vấn đề của Java hiện đại. Các phương thức Stream và thư viện số được trình bày ở đây vẫn đang được hỗ trợ. Ví dụ độc lập chạy với **Java 17+**.

## 1. Reduction tính tổng diễn ra thế nào?

Ba cách dưới đây cùng mang ý định cộng các phần tử của một Stream **int**:

~~~java
int a = java.util.stream.IntStream.of(2, 3, 5).sum();
int b = java.util.stream.IntStream.of(2, 3, 5)
        .reduce(0, Integer::sum);
int c = java.util.stream.IntStream.of(2, 3, 5)
        .reduce(0, (left, right) -> left + right);
~~~

Đây là các đoạn minh họa (không phải ba chương trình độc lập); cả ba biến đều bằng **10**. **sum()** là terminal operation chuyên dụng, còn **reduce(identity, accumulator)** là biến thể tổng quát:

~~~text
Nguồn → các intermediate operation → terminal reduction
2, 3, 5                       → ((0 + 2) + 3) + 5 = 10
        identity = 0             accumulator = cộng hai giá trị
~~~

Với kiểu nguyên, giá trị **0** là identity của cộng, **1** là identity của nhân. Với **Stream.reduce(...)** dùng song song, phép kết hợp phải **associative** (tính kết hợp), **stateless** (không phụ thuộc trạng thái ngoài) và **non-interfering** (không sửa nguồn). Hệ thống có thể chia dữ liệu ra nhiều nhánh và ghép kết quả trung gian theo nhóm khác với thứ tự nhìn thấy trong code.

Điểm cần ghi nhớ: **reduce không tự làm phép toán trở nên an toàn về phạm vi số hoặc chính xác hơn về sai số.** Kết quả bị chi phối bởi kiểu dữ liệu và phép cộng thật sự sử dụng.

## 2. Tràn số nguyên: kết quả vượt phạm vi int/long

| Kiểu Java | Số bit | Phạm vi |
|---|---:|---|
| **int** | 32 | -2.147.483.648 đến 2.147.483.647 |
| **long** | 64 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Ví dụ, phép toán học **2.147.483.647 + 1 = 2.147.483.648** không còn nằm trong phạm vi **int**. Java dùng số nguyên bù hai: với phép cộng nguyên thông thường, các bit vượt ra ngoài phạm vi bị bỏ, nên kết quả **int** trở thành **-2.147.483.648**.

~~~java
int wrapped = Integer.MAX_VALUE + 1;
// wrapped == Integer.MIN_VALUE (-2147483648)
~~~

Hành vi này cũng xảy ra trong các reduction sử dụng phép cộng nguyên thông thường:

~~~java
int wrong = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, 1)
        .sum();
// wrong == -2147483648
~~~

**IntStream.sum()**, **IntStream.reduce(0, Integer::sum)** và **Collectors.summingInt(...)** không có cơ chế tự kiểm tra overflow cho tổng nguyên. **LongStream.sum()** và phép cộng **long** thông thường cũng có nguy cơ tràn nếu tổng thực sự quá lớn đối với **long**. Việc đổi từ **int** sang **long** làm tăng phạm vi, nhưng không mang lại độ chính xác nguyên không giới hạn.

Điều nguy hiểm là chương trình **vẫn chạy**, thường không có ngoại lệ. Giá trị bị sai có thể tiếp tục đi vào thống kê, giới hạn ngân sách hoặc quy tắc nghiệp vụ.

### 2.1. Mở rộng kiểu trước khi tính

Nếu đầu vào là **int**, nhưng biết tổng kết quả có thể vượt **int** và vẫn nằm trong **long**, chuyển các phần tử sang **long trước phép cộng**:

~~~java
long total = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// total == 2147483648L
~~~

Với danh sách đối tượng, có thể dùng **mapToLong(...)** để xác lập kiểu tính tổng:

~~~java
// Giả sử quantities có kiểu List<Integer>
long total = quantities.stream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Đoạn trên là minh họa phụ thuộc biến **quantities** được khai báo ở nơi gọi.

**Cẩn thận với thời điểm ép kiểu khi tính trung gian:**

~~~java
int x = 1_500_000_000;
int y = 2;

// Sai mục đích: phép nhân int đã tràn trước khi ép lên long.
long tooLate = (long) (x * y);

// Đúng: thực hiện phép nhân bằng long.
long widened = (long) x * y;
// widened == 3000000000L
~~~

Nguyên tắc chung: **ép sang kiểu đủ rộng trước phép tính có nguy cơ tràn**, kể cả trong **map**, **filter**, **reduce** hoặc biểu thức tính tiền từng dòng. Nếu bản thân giá trị tổng có thể vượt **long**, chọn **BigInteger** hoặc thiết kế lại miền dữ liệu.

### 2.2. Phát hiện overflow bằng Math.*Exact

Thư viện **Math** có các phương thức kiểm tra phạm vi, như:

- **Math.addExact(int, int)** và **Math.addExact(long, long)**.
- **Math.subtractExact(...)**, **Math.multiplyExact(...)**.
- **Math.toIntExact(long)** khi thu hẹp một **long** về **int**.

Khi vượt phạm vi, các hàm tương ứng ném **ArithmeticException**. Với tổng nguyên, dùng:

~~~java
int checked = java.util.stream.IntStream
        .of(1_000_000_000, 1_000_000_000)
        .reduce(0, Math::addExact);
// checked == 2000000000
~~~

Nếu cộng thêm **1_000_000_000** nữa, reduction có thể ném **ArithmeticException** thay vì trả một tổng âm không mong đợi. Đây là lựa chọn phù hợp khi **tràn phải được coi là lỗi**, cần hiển thị hoặc xử lý rõ ràng tại tầng nghiệp vụ.

**Giới hạn quan trọng:** **Math.addExact** kiểm tra **mỗi lần cộng trung gian**, không chỉ kiểm tra tổng cuối. Với dãy **[Integer.MAX_VALUE, 1, -1]**, tổng toán học cuối cùng bằng **Integer.MAX_VALUE** và vừa phạm vi **int**. Tuy vậy, reduction tuần tự tính từ trái sang phải sẽ ném ngoại lệ ngay tại bước cộng **MAX_VALUE + 1**. Khi chạy song song, cách chia nhóm cũng có thể thay đổi nơi xuất hiện lỗi. Vì thế đừng dùng **Math.addExact** như một phép kiểm tra duy nhất rằng *tổng cuối* có nằm trong phạm vi hay không nếu các tổng trung gian có thể vượt giới hạn; hãy tính trong kiểu đủ rộng hoặc **BigInteger** rồi kiểm tra khi chuyển về kiểu đích.

### 2.3. BigInteger cho tổng nguyên lớn hoặc không biết giới hạn

**BigInteger** là số nguyên có độ chính xác tùy ý, chỉ bị giới hạn thực tế bởi tài nguyên hệ thống. Với dữ liệu có khả năng vượt **long**:

~~~java
java.math.BigInteger total = java.util.stream.Stream
        .of("9223372036854775807", "1")
        .map(java.math.BigInteger::new)
        .reduce(java.math.BigInteger.ZERO,
                java.math.BigInteger::add);
// total.toString() == "9223372036854775808"
~~~

**BigInteger.ZERO** là identity; **BigInteger::add** cộng số nguyên chính xác, không tràn kiểu cố định. **BigInteger** là immutable nên phù hợp với dạng reduction thuần hàm, kể cả khi chia nhóm xử lý song song.

Nếu cần thu hẹp kết quả trở lại **int** hoặc **long**, dùng **intValueExact()** hoặc **longValueExact()** để kiểm tra phạm vi. **intValue()** và **longValue()** có thể làm mất các bit cao; tránh dùng chúng khi dữ liệu phải chính xác.

Chỉ dùng **BigInteger** khi thực sự cần: đối tượng và phép toán số lớn có chi phí bộ nhớ/CPU cao hơn kiểu nguyên thủy.

## 3. Sai số số thực: vì sao 0.1 + 0.2 không đúng bằng 0.3?

**float** và **double** dùng biểu diễn dấu chấm động nhị phân theo IEEE 754. **double** có 53 bit độ chính xác phần định trị (xấp xỉ 15–17 chữ số thập phân có nghĩa), nhưng **không thể lưu chính xác mọi phân số thập phân**, chẳng hạn **0.1** và **0.2**.

~~~java
double result = 0.1 + 0.2;
System.out.println(result);
// 0.30000000000000004
~~~

Giá trị này không phải lỗi riêng của Stream; nó xuất hiện ngay ở phép cộng thông thường. Một reduction cộng nhiều số có thể **tích lũy sai số làm tròn**. Điều này quan trọng khi tính số liệu khoa học, tỷ lệ, tổng lượng đo hoặc số tiền.

Các tính chất cần phân biệt:

1. **Overflow số nguyên:** kết quả nhảy sang giá trị khác trong phạm vi kiểu nguyên do bỏ bit cao.
2. **Sai số số thực:** kết quả vẫn có thể hữu hạn nhưng khác kết quả toán học do làm tròn.
3. **Overflow số thực:** kết quả có thể trở thành **Infinity** hoặc **-Infinity** khi độ lớn vượt khả năng biểu diễn.
4. **NaN:** giá trị đặc biệt "Not a Number" có thể lan truyền khi tính toán (ví dụ **Infinity + -Infinity**).

**double** không dùng cơ chế wraparound như **int** khi vượt biên. **Math.addExact** cũng không có overload **double** để biến phép cộng số thực thành phép cộng thập phân chính xác.

### 3.1. Tính cộng không còn kết hợp tuyệt đối với double

Trong toán học thực, phép cộng kết hợp:

~~~text
(a + b) + c = a + (b + c)
~~~

Nhưng với phép toán **double** đã làm tròn sau mỗi bước, hai cách nhóm có thể khác nhau:

~~~java
double firstOrder = java.util.stream.DoubleStream
        .of(1e16, 1.0, -1e16)
        .reduce(0.0, Double::sum);

double secondOrder = java.util.stream.DoubleStream
        .of(1e16, -1e16, 1.0)
        .reduce(0.0, Double::sum);

// firstOrder == 0.0
// secondOrder == 1.0
~~~

Ở thứ tự đầu, khi cộng **1e16 + 1.0**, số **1.0** quá nhỏ so với đơn vị làm tròn gần **1e16** nên bị mất. Sau đó trừ **1e16** cho kết quả **0.0**. Ở thứ tự thứ hai, hai số lớn triệt tiêu trước, nên **1.0** còn lại.

Vì phép cộng dấu chấm động không có tính kết hợp chính xác, **reduce(0.0, Double::sum)** không đáp ứng hoàn toàn điều kiện toán học của một reducer associative. Trên stream song song, cách chia nhóm và gộp các phần có thể thay đổi các bước làm tròn. Do đó **đừng hứa số liệu double reduction bất biến từng bit chỉ vì đầu vào giống nhau**.

### 3.2. DoubleStream.sum() khác reduce(0.0, Double::sum)

**DoubleStream.sum()** là thao tác chuyên dụng để cộng các phần tử **double**. Theo Java API, việc thực hiện phép cộng **không được ràng buộc vào một thứ tự cố định**. Java có thể sử dụng kỹ thuật **compensated summation** hoặc thuật toán khác để giảm sai số so với cộng **double** tuần tự đơn giản.

Vì vậy, trong code thông thường muốn tính tổng **double**, **ưu tiên DoubleStream.sum()** để thư viện có cơ hội dùng thuật toán cải thiện độ chính xác:

~~~java
double estimate = java.util.stream.DoubleStream
        .of(0.1, 0.2, 0.3)
        .sum();
~~~

Không khẳng định **estimate** có biểu diễn thập phân chính xác bằng **0.6** trong mọi triển khai, cũng không khẳng định bằng kết quả của **reduce(0.0, Double::sum)**. **DoubleStream.sum()** có thể trả kết quả khác nhau nếu thứ tự cộng hoặc thuật toán thực thi thay đổi, ngay với cùng đầu vào.

Nếu tổng các số hữu hạn rất lớn, kết quả hoặc các tổng trung gian có thể thành vô cực; nếu đầu vào chứa **NaN**, tổng trả **NaN**. Khi tổng có giá trị vô cực trái dấu, kết quả có thể thành **NaN**. Kiểm tra miền đầu vào và ý nghĩa của các giá trị không hữu hạn trong nghiệp vụ, thay vì coi mọi **double** đều là số đo thông thường.

### 3.3. Khác biệt giữa độ chính xác và tính tái lập

- **Độ chính xác số học:** kết quả gần tổng toán học thực đến mức nào.
- **Tính tái lập:** chạy lại với cùng dữ liệu có cho đúng cùng bit kết quả hay không.
- **Tính đúng nghiệp vụ:** sai số có chấp nhận được theo đơn vị, mức dung sai hoặc quy định của lĩnh vực hay không.

Một thuật toán có thể có sai số nhỏ hơn nhưng không đảm bảo cùng thứ tự cộng; một reduction tuần tự với thứ tự cố định có thể dễ tái lập hơn nhưng vẫn sai số đáng kể. Nếu cần giá trị thập phân **chính xác theo đơn vị nghiệp vụ**, thường chọn **BigDecimal** hoặc số nguyên biểu diễn đơn vị nhỏ nhất thay vì dựa vào một thuật toán tổng **double**.

## 4. BigDecimal: phép tính thập phân đúng theo giá trị đầu vào

**BigDecimal** là kiểu thập phân có độ chính xác tùy ý; có thể biểu diễn chính xác **0.1**, **0.2** và tổng **0.3** nếu tạo từ văn bản thập phân:

~~~java
java.math.BigDecimal decimalTotal = java.util.stream.Stream
        .of("0.1", "0.2")
        .map(java.math.BigDecimal::new)
        .reduce(java.math.BigDecimal.ZERO,
                java.math.BigDecimal::add);
// decimalTotal.toPlainString() == "0.3"
~~~

**Chọn cách khởi tạo đúng là then chốt:**

| Cách tạo | Ý nghĩa |
|---|---|
| **new BigDecimal("0.1")** | Chính xác số thập phân 0.1 |
| **BigDecimal.valueOf(0.1)** | Chuyển từ biểu diễn chuỗi chuẩn của double 0.1 thành BigDecimal; ở ví dụ này là 0.1 |
| **new BigDecimal(0.1)** | Giữ chính xác giá trị nhị phân gần 0.1 đã được lưu trong double, không phải thập phân 0.1 |
| **new BigDecimal(0.1 + 0.2)** | Giữ kết quả double đã bị làm tròn trước đó; không sửa lại phép cộng sai |

Khi đầu vào vốn là số thập phân từ API/database (ví dụ hóa đơn), nên chuyển từ **String** hay kiểu decimal thích hợp ngay từ nguồn. **Đổi sang BigDecimal sau khi đã cộng sai bằng double không khôi phục được độ chính xác bị mất.**

Với **BigDecimal::add** không truyền **MathContext** làm tròn, việc cộng các giá trị decimal có thể xem là phép cộng chính xác và phù hợp reduction. Tuy nhiên, nếu đặt chế độ làm tròn ở **mỗi lần cộng** bằng **add(other, mathContext)**, thứ tự cộng có thể ảnh hưởng kết quả; cần thiết kế quy tắc rounding nhất quán.

**BigDecimal không tự quyết định số chữ số sau dấu phẩy cho tiền.** Hãy áp dụng **setScale(...)** hoặc quy tắc làm tròn theo miền nghiệp vụ tại bước phù hợp; phép chia decimal không có kết quả hữu hạn có thể cần chỉ rõ **scale** và **RoundingMode**.

Một lưu ý khi đối chiếu kết quả:

~~~java
new java.math.BigDecimal("0.30")
        .compareTo(new java.math.BigDecimal("0.3")) == 0; // true

new java.math.BigDecimal("0.30")
        .equals(new java.math.BigDecimal("0.3")); // false
~~~

**equals** phân biệt scale, còn **compareTo** đối chiếu giá trị số học. Không dùng **equals** cho hai decimal khác scale nếu nghiệp vụ chỉ quan tâm giá trị số.

## 5. Ví dụ chạy đầy đủ: nhận diện, phát hiện và sửa lỗi

Lưu toàn bộ mã thành **ReductionPitfalls.java**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ReductionPitfalls {
    public static void main(String[] args) {
        int wrapped = IntStream.of(Integer.MAX_VALUE, 1).sum();
        System.out.println("int sum = " + wrapped);

        try {
            int checked = IntStream.of(Integer.MAX_VALUE, 1)
                    .reduce(0, Math::addExact);
            System.out.println(checked);
        } catch (ArithmeticException exception) {
            System.out.println("checked overflow");
        }

        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();
        System.out.println("long sum = " + widened);

        BigInteger bigTotal = IntStream.of(Integer.MAX_VALUE, 1)
                .mapToObj(value -> BigInteger.valueOf(value))
                .reduce(BigInteger.ZERO, BigInteger::add);
        System.out.println("big sum = " + bigTotal);

        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));

        double orderA = DoubleStream.of(1e16, 1.0, -1e16)
                .reduce(0.0, Double::sum);
        double orderB = DoubleStream.of(1e16, -1e16, 1.0)
                .reduce(0.0, Double::sum);
        System.out.println("order A = " + orderA);
        System.out.println("order B = " + orderB);

        BigDecimal decimal = Stream.of("0.1", "0.2")
                .map(BigDecimal::new)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("decimal = " + decimal.toPlainString());
    }
}
~~~

Tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ReductionPitfalls.java
java ReductionPitfalls
~~~

**Stdout xác định:**

~~~text
int sum = -2147483648
checked overflow
long sum = 2147483648
big sum = 2147483648
0.1 + 0.2 = 0.30000000000000004
order A = 0.0
order B = 1.0
decimal = 0.3
~~~

Phân tích các điểm trong output:

1. **int sum** bị tràn, âm mặc dù cả hai đầu vào đều dương.
2. **checked overflow** xuất hiện do **Math.addExact** bắt lỗi tại phép cộng vượt phạm vi.
3. **long sum** và **big sum** đều biểu diễn đúng giá trị toán học **2.147.483.648**.
4. **0.1 + 0.2** cho thấy sai số biểu diễn nhị phân.
5. **order A/B** cho thấy thứ tự cộng trong reduction số thực có thể làm mất hoặc giữ lại số nhỏ.
6. **decimal** biểu diễn chính xác phép cộng thập phân vì đầu vào được tạo trực tiếp từ chuỗi.

Mỗi phép thử tạo **một Stream mới**. Stream đã chạy terminal operation như **sum()** hoặc **reduce()** không thể được tiêu thụ lần hai.

## 6. Ví dụ nghiệp vụ: tổng số tiền theo đơn vị nhỏ nhất

Một phương án hiệu quả khi đơn vị nghiệp vụ có số chữ số thập phân cố định là dùng **long** biểu diễn **đơn vị nhỏ nhất** (ví dụ cent), tính và kiểm tra overflow, rồi chỉ đổi định dạng khi hiển thị. Ví dụ Java 17+, lưu thành **MoneyReductionExample.java**:

~~~java
import java.math.BigDecimal;
import java.util.List;

public class MoneyReductionExample {
    record Line(long unitPriceCents, int quantity) {}

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line(1999, 2),
                new Line(450, 1)
        );

        long totalCents = lines.stream()
                .mapToLong(line -> Math.multiplyExact(
                        line.unitPriceCents(), (long) line.quantity()))
                .reduce(0L, Math::addExact);

        BigDecimal amount = BigDecimal.valueOf(totalCents, 2);
        System.out.println("cents = " + totalCents);
        System.out.println("amount = " + amount.toPlainString());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MoneyReductionExample.java
java MoneyReductionExample
~~~

~~~text
cents = 4448
amount = 44.48
~~~

- **Math.multiplyExact** bảo vệ phép nhân giá đơn vị với số lượng.
- **Math.addExact** bảo vệ cộng tổng tích lũy.
- **BigDecimal.valueOf(totalCents, 2)** biểu diễn giá trị với hai chữ số thập phân, không qua **double**.
- **record** trong ví dụ là cú pháp Java 16+; việc chọn số nguyên đơn vị nhỏ nhất và các phương thức kiểm tra overflow vẫn phù hợp với Java hiện đại.

Cách này phù hợp khi đã định nghĩa rõ hệ đơn vị và miền giá trị nằm trong **long**. Nếu có tỷ giá, thuế, lãi, phần lẻ nhỏ hơn đơn vị được lưu hoặc quy tắc làm tròn phức tạp, cần mô hình **BigDecimal**, scale và **RoundingMode** theo yêu cầu nghiệp vụ. Nếu số lượng hoặc tiền trung gian có thể vượt **long**, dùng số lớn hoặc xử lý riêng.

## 7. Chọn kiểu số và chiến lược reduction

| Nhu cầu | Lựa chọn nên cân nhắc | Điều kiện/cảnh báo |
|---|---|---|
| Tổng **int** chắc chắn vừa phạm vi | **IntStream.sum()** | Phải có giới hạn đầu vào đáng tin; không phát hiện tràn |
| Tổng các **int** có thể vượt int nhưng vừa long | **asLongStream().sum()**, **mapToLong(...).sum()** | Mở rộng kiểu trước phép toán; tổng vẫn phải vừa long |
| Phát hiện tràn khi cộng/nhân | **Math.addExact**, **Math.multiplyExact** | Bắt cả overflow trung gian; có thể ném dù tổng cuối vừa phạm vi |
| Tổng nguyên vượt cả long | **BigInteger::add** | Chính xác, tốn tài nguyên hơn |
| Số thực đo đạc, chấp nhận dung sai | **DoubleStream.sum()** | Không chính xác tuyệt đối; thứ tự/thuật toán có thể thay đổi kết quả |
| Số tiền hoặc số decimal cần chính xác | **BigDecimal** từ nguồn decimal hoặc **long** đơn vị nhỏ nhất | Xác lập scale, rounding và giới hạn dữ liệu |
| Kiểm tra tổng trong một khoảng số học | **long/BigInteger/BigDecimal** tùy miền | Không kiểm tra trên tổng đã bị tràn hoặc sai số quá lớn |

**Không có một kiểu tối ưu cho mọi bài toán.** Đầu tiên xác định đơn vị, cận giá trị đầu vào, số lượng phần tử, độ chính xác, dung sai và quy tắc làm tròn. Sau đó mới chọn **sum()**, **reduce()**, **BigInteger** hoặc **BigDecimal**.

## 8. Sai lầm dễ gặp trong Stream và reduction

### Sai lầm 1: Nghĩ sum() tự kiểm tra tràn

~~~java
int total = records.stream().mapToInt(Record::amount).sum();
~~~

Đoạn trên chỉ là minh họa khi có kiểu **Record** và danh sách **records** tương ứng. Nếu một phần tổng vượt phạm vi **int**, tổng có thể sai mà không có ngoại lệ. Kiểm soát miền dữ liệu hoặc chuyển kiểu thích hợp, rồi dùng **Math.*Exact** nếu cần kiểm tra.

### Sai lầm 2: Tính bằng int rồi mới gán long

~~~java
long total = quantities.stream()
        .mapToInt(Integer::intValue)
        .sum(); // sum() trả int; gán long sau đó không sửa overflow
~~~

Thay bằng **mapToLong(Integer::longValue).sum()** hoặc **mapToInt(...).asLongStream().sum()** để cộng trực tiếp bằng **long**.

### Sai lầm 3: Cho rằng stream song song luôn cho cùng tổng double

~~~java
double total = values.parallelStream()
        .mapToDouble(Double::doubleValue)
        .reduce(0.0, Double::sum);
~~~

Đoạn này là minh họa khi **values** có kiểu **List<Double>**. Phép cộng **double** không associative chính xác; việc nhóm các phép tính có thể khiến bit kết quả khác. Không viết test chỉ dựa vào **==** với một giá trị decimal mong đợi nếu không có yêu cầu bảo đảm chính xác từng bit.

### Sai lầm 4: Đối chiếu double với == cho kỳ vọng thập phân

~~~java
double actual = 0.1 + 0.2;
boolean exactMatch = (actual == 0.3); // false
~~~

Nếu phép đo được chấp nhận trong sai số, dùng một **tolerance** được định nghĩa theo nghiệp vụ, có xét đến độ lớn của số và kiểm tra **Double.isFinite(...)** khi cần. Ví dụ đơn giản với các số hữu hạn có độ lớn vừa phải:

~~~java
double expected = 0.3;
double tolerance = 1e-12;
boolean approximatelyEqual =
        Math.abs(actual - expected) <= tolerance; // true
~~~

Giá trị **1e-12** chỉ để minh họa, không phải dung sai dùng chung cho tài chính, đo lường và mọi độ lớn số. Đối với tiền cần khớp chính xác, dùng **BigDecimal** hoặc đơn vị nhỏ nhất.

### Sai lầm 5: Dùng BigDecimal(double) để sửa sai số

~~~java
java.math.BigDecimal unexpected = new java.math.BigDecimal(0.1);
java.math.BigDecimal intended = new java.math.BigDecimal("0.1");
~~~

Hai giá trị này không hoàn toàn bằng nhau: **unexpected** chứa giá trị chính xác của số **double** gần 0.1, còn **intended** chứa chính xác số decimal 0.1. Chọn cách khởi tạo theo nguồn dữ liệu, không giả định chuyển kiểu có thể đảo ngược mọi sai số đã phát sinh.

### Sai lầm 6: Dùng container mutable tùy ý trong reduce

~~~java
// Không dùng một List/array/shared mutable object làm identity của
// reduce() rồi sửa nó trong accumulator khi tính song song.
~~~

**reduce** dành cho kết hợp theo phép toán phù hợp với các luật identity/associativity. Với đối tượng tích lũy mutable, nên sử dụng **collect()** với supplier, accumulator và combiner phù hợp; đừng dùng biến tổng ngoài pipeline rồi cộng trong **forEach** song song mà thiếu cơ chế đồng bộ. Kể cả khi tránh được race condition, sai số **double** vẫn có thể tồn tại.

### Sai lầm 7: Quên kết quả của nguồn rỗng

Với **IntStream.sum()**, tổng stream rỗng là **0**. Với **IntStream.reduce(0, Integer::sum)** cũng là **0**, trong khi **IntStream.reduce(Integer::sum)** (không truyền identity) trả **OptionalInt.empty()** nếu nguồn trống.

~~~java
int emptySum = java.util.stream.IntStream.empty().sum(); // 0
java.util.OptionalInt emptyReduction =
        java.util.stream.IntStream.empty().reduce(Integer::sum);
// emptyReduction.isEmpty() == true (Java 11+)
~~~

Hãy phân biệt **"tổng bằng 0"** với **"không có phần tử để tính"** nếu nghiệp vụ cần biết nguồn có dữ liệu hay không.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Hai giá trị **1_600_000_000** được cộng bằng **IntStream.sum()**. Tổng có chính xác là **3_200_000_000** không?

**Câu 2.** Vì sao **long total = intStream.sum()** không phòng được overflow? Cách sửa khi tổng vẫn vừa **long**?

**Câu 3.** Tổng toán học của dãy **Integer.MAX_VALUE, 1, -1** vừa phạm vi **int**. Vì sao **reduce(0, Math::addExact)** tuần tự vẫn có thể ném ngoại lệ?

**Câu 4.** **DoubleStream.sum()** có bảo đảm chính xác tuyệt đối hay kết quả không đổi từng bit giữa mọi lần chạy không?

**Câu 5.** Với các giá trị tiền thập phân **"0.10", "0.20", "0.30"**, nên tạo **BigDecimal** thế nào và dùng reduction nào?

**Đáp án:**

1. **Không.** Tổng vượt **Integer.MAX_VALUE** và **int** bị tràn. Dùng kiểu đủ rộng trước khi cộng.
2. **sum() đã thực hiện phép cộng bằng int**; ép giá trị kết quả sang long xảy ra quá muộn. Dùng **intStream.asLongStream().sum()** hoặc **mapToLong(...).sum()**.
3. Phép cộng trung gian **MAX_VALUE + 1** vượt giới hạn dù các số về sau làm tổng trở lại phạm vi hợp lệ. **Math.addExact** kiểm tra ở từng bước.
4. **Không.** API cho phép thay đổi thứ tự và kỹ thuật cộng để tối ưu độ chính xác/hiệu năng; bản chất **double** có làm tròn.
5. Tạo từ chuỗi bằng **new BigDecimal("0.10")** (tương tự hai giá trị còn lại), rồi dùng **reduce(BigDecimal.ZERO, BigDecimal::add)**; áp dụng rounding theo chính sách miền nghiệp vụ nếu cần.

## 10. Ghi nhớ và tài liệu chính thức

- Xác định **giới hạn miền số trước reduction**. Nếu tổng nguyên có nguy cơ vượt **int**, mở rộng kiểu trước khi cộng; nếu vượt **long**, dùng **BigInteger**.
- Dùng **Math.addExact/multiplyExact** khi overflow của phép toán trung gian phải được phát hiện; đừng dùng chúng để suy luận duy nhất về phạm vi tổng toán học cuối cùng.
- **double** phù hợp cho tính gần đúng có dung sai, nhưng **không phải thập phân chính xác**. **DoubleStream.sum()** có thể giảm sai số mà không bảo đảm chính xác tuyệt đối hoặc thứ tự cố định.
- Dùng **BigDecimal** hoặc integer theo đơn vị nhỏ nhất khi giá trị thập phân phải chính xác; quyết định **rounding** theo nghiệp vụ.
- Với parallel reduction, hiểu tính **associativity** và thứ tự kết hợp; không dùng shared mutable state trong accumulator.

Nguồn tham khảo (Java API hiện hành):

- [Stream.reduce và hợp đồng phép kết hợp — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [IntStream.sum và reduce — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [DoubleStream.sum và độ chính xác số thực — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html)
- [Math.addExact, multiplyExact — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
- [BigInteger — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html)
- [BigDecimal — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html)
