# Phân tích bài toán thành dữ liệu vào, xử lý và kết quả (Java 17+)

## 1. Mục tiêu: hiểu bài toán trước khi viết mã

Khi nhận một yêu cầu bằng ngôn ngữ tự nhiên, đừng bắt đầu bằng việc viết ngay `Scanner`, `if` hay vòng lặp. Trước hết hãy trả lời ba câu hỏi theo mô hình **Input – Process – Output (IPO)**:

1. **Input (dữ liệu vào):** Chương trình cần biết những giá trị nào, đến từ đâu, có kiểu dữ liệu, đơn vị, giới hạn và điều kiện hợp lệ gì?
2. **Process (xử lý):** Phải kiểm tra, biến đổi, tính toán và áp dụng quy tắc nghiệp vụ nào, theo thứ tự nào?
3. **Output (kết quả):** Chương trình phải trả lại hoặc hiển thị những gì, dưới dạng nào, làm sao biết kết quả đúng và phải phản hồi thế nào khi dữ liệu vào sai?

Phân tích IPO biến một đề bài chung chung thành một **hợp đồng có thể triển khai và kiểm thử**. Với Java, ba phần thường tương ứng với bước đọc tham số/input, một hoặc nhiều phương thức xử lý, rồi bước hiển thị hoặc trả kết quả.

```text
Yêu cầu người dùng
      |
      v
Input: dữ liệu + điều kiện hợp lệ
      |
      v
Process: kiểm tra -> tính toán -> quyết định
      |
      v
Output: kết quả thành công HOẶC thông báo lỗi
      |
      v
Đối chiếu với các trường hợp thử đã xác định
```

Mô hình này phù hợp với bài tập console, hàm tính toán, xử lý file, API và các chương trình lớn hơn. **IPO là cách phân tích**, không phải cú pháp hoặc một kiểu dữ liệu có sẵn trong Java.

## 2. Phân tích một đề bài cụ thể

**Đề bài mẫu:** *Nhập điểm của ba môn học. Mỗi điểm nằm trong khoảng từ 0 đến 10. Tính điểm trung bình cộng. Kết luận PASS nếu điểm trung bình ít nhất 5,0 **và** cả ba điểm đều từ 4,0 trở lên; ngược lại là FAIL. Nếu dữ liệu không hợp lệ, thông báo lỗi thay vì tính kết quả.*

Từ đề này, lập bảng:

| Thành phần | Phân tích | Quyết định khi cài đặt |
| --- | --- | --- |
| Input | Ba điểm số `score1`, `score2`, `score3` | Dùng `double` để chấp nhận điểm lẻ |
| Miền hợp lệ | Mỗi điểm hữu hạn và `0 <= score <= 10` | Kiểm tra trước khi tính |
| Process – công thức | `average = (score1 + score2 + score3) / 3.0` | Chia cho `3.0` để biểu đạt phép chia số thực |
| Process – điều kiện | `average >= 5.0` **và** ba điểm `>= 4.0` | Dùng `&&` giữa bốn điều kiện |
| Output thành công | Trung bình với hai chữ số thập phân và `PASS`/`FAIL` | `printf(Locale.ROOT, "%.2f")` và thông báo trạng thái |
| Output lỗi | Không có kết luận nếu thiếu/sai điểm | Thông báo cụ thể ở trường đầu tiên không hợp lệ |
| Quy tắc gần ngưỡng | So sánh điểm trung bình **chưa làm tròn** | Chỉ định dạng hai chữ số khi hiển thị |

Tại sao kiểm tra `Double.isFinite()`? `Double.parseDouble("NaN")` và `Double.parseDouble("Infinity")` có thể tạo giá trị `double` đặc biệt không phải điểm hợp lệ. Chỉ kiểm tra bằng các phép so sánh với `0` và `10` là chưa đủ đối với `NaN`, vì các so sánh thứ tự với `NaN` đều cho `false`.

### Làm rõ yêu cầu còn mơ hồ

Trong dự án thực tế, nên làm rõ những trường hợp đề bài chưa quy định:

- Cho phép điểm âm, điểm trên 10, giá trị rỗng, giá trị `NaN` không? Ví dụ này quy định **không**.
- Có giới hạn số chữ số thập phân đầu vào không? Ví dụ **không** giới hạn riêng, miễn số hợp lệ trong miền.
- Khi điểm trung bình là `4.999...`, nên so sánh trước hay sau làm tròn? Ví dụ so sánh **giá trị tính được**, làm tròn chỉ để in.
- Khi nhập sai một trường, yêu cầu nhập lại hay báo lỗi và dừng? Ví dụ **báo lỗi và kết thúc**.
- Nhập từ bàn phím, file, tham số `main`, hay API? Ví dụ console đọc **ba dòng**, lần lượt là ba điểm.

Những lựa chọn này thuộc **hợp đồng của bài mẫu**, không phải quy tắc mặc định của tất cả ứng dụng chấm điểm.

## 3. Tách dữ liệu vào khỏi phần xử lý

Thói quen tốt là phân biệt rõ **cách nhận dữ liệu** với **quy tắc tính toán**. Chẳng hạn cùng một phép tính trung bình có thể được gọi từ chương trình console, bài kiểm thử hay một API.

Phân ranh giới:

- **Tầng Input:** đọc ba chuỗi; kiểm tra có dữ liệu, parse số; từ chối giá trị không hợp lệ. `Scanner` và `Double.parseDouble` nằm ở đây.
- **Tầng Process:** chỉ nhận ba số đã hợp lệ; tính trung bình và quyết định PASS/FAIL. Tầng này không cần biết người dùng nhập bằng cách nào.
- **Tầng Output:** nhận kết quả xử lý rồi in ra theo định dạng đã thống nhất. Không tính lại công thức nghiệp vụ ở câu lệnh `println`.

Cách tách này giúp một lỗi không bị trộn lẫn: nếu `abc` không được chấp nhận thì xem Input; nếu điểm 4, 5, 6 bị đánh FAIL thì xem Process; nếu in `5,00` thay vì `5.00` thì xem Output/locale.

## 4. Chuyển IPO thành thuật toán

Trước khi code, có thể viết **giả mã** độc lập với Java:

```text
Đọc score1, score2, score3 (mỗi điểm từ một dòng).
Với từng điểm:
    Nếu không có dòng -> báo thiếu dữ liệu và dừng.
    Nếu không thể parse thành số thực -> báo sai định dạng và dừng.
    Nếu không hữu hạn hoặc ngoài [0, 10] -> báo ngoài phạm vi và dừng.

average = (score1 + score2 + score3) / 3.0
passed = average >= 5.0
         AND score1 >= 4.0
         AND score2 >= 4.0
         AND score3 >= 4.0

In điểm trung bình với 2 chữ số thập phân.
In PASS nếu passed, ngược lại in FAIL.
```

Giả mã giúp kiểm tra trình tự trước khi viết cú pháp: **xác thực → tính toán → quyết định → trình bày**. Nếu tính trước khi biết dữ liệu hợp lệ, chương trình có thể truyền giá trị vô nghĩa vào xử lý hoặc vô tình công bố một kết quả sai.

Điều kiện trong Java viết:

```java
boolean passed = average >= 5.0
        && score1 >= 4.0
        && score2 >= 4.0
        && score3 >= 4.0;
```

Đây là đoạn biểu thức minh họa, cần đặt nơi các biến đã được khai báo. Toán tử `&&` có nghĩa **và**, khác `||` (hoặc). Nếu thay nhầm bằng `||`, học sinh có điểm một môn thấp vẫn có thể được kết luận PASS.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`GradeReport.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class GradeReport {
    record Result(double average, boolean passed) {}

    static double readScore(Scanner scanner, String label) {
        if (!scanner.hasNextLine()) {
            throw new IllegalArgumentException("missing " + label);
        }

        String text = scanner.nextLine().trim();
        final double value;

        try {
            value = Double.parseDouble(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid " + label);
        }

        if (!Double.isFinite(value) || value < 0 || value > 10) {
            throw new IllegalArgumentException("out of range " + label);
        }
        return value;
    }

    static Result evaluate(double first, double second, double third) {
        double average = (first + second + third) / 3.0;
        boolean passed = average >= 5.0
                && first >= 4.0
                && second >= 4.0
                && third >= 4.0;
        return new Result(average, passed);
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            try {
                System.out.println("Score 1:");
                double first = readScore(scanner, "score1");

                System.out.println("Score 2:");
                double second = readScore(scanner, "score2");

                System.out.println("Score 3:");
                double third = readScore(scanner, "score3");

                Result result = evaluate(first, second, third);
                System.out.printf(Locale.ROOT,
                        "Average: %.2f%n", result.average());
                System.out.println("Result: "
                        + (result.passed() ? "PASS" : "FAIL"));
            } catch (IllegalArgumentException ex) {
                System.out.println("Error: " + ex.getMessage());
            }
        }
    }
}
```

`record Result` là cú pháp ổn định trong Java 17. Nó gom hai kết quả logic `average` và `passed`, tự cung cấp các accessor `average()` và `passed()`. Với bài đơn giản, có thể không cần record; tuy nhiên đối tượng kết quả giúp phân biệt dữ liệu và cách hiển thị.

**Vai trò từng phương thức:**

- `readScore(...)` thuộc **Input**. Nó đọc một dòng, parse `double`, kiểm tra số hữu hạn và miền điểm; đầu vào sai làm phát sinh `IllegalArgumentException`.
- `evaluate(...)` thuộc **Process**. Nó không đọc console và không in gì; với ba điểm hợp lệ, trả `Result`.
- `main(...)` điều phối các bước và thuộc **Output** ở hai câu lệnh cuối. Nếu bắt lỗi input, nó chỉ in `Error: ...` rồi kết thúc.

`Double.parseDouble` dùng dấu chấm thập phân theo cú pháp Java, **không parse theo locale hiển thị của máy**. `Locale.ROOT` chỉ được dùng tại lúc in kết quả để đảm bảo dấu chấm trong output mẫu.

### Biên dịch và chạy

Từ thư mục chứa `GradeReport.java`, tạo thư mục `out` nếu chưa có:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out GradeReport.java
java -cp out GradeReport
```

Có thể chạy trên PowerShell, CMD, bash với JDK 17+. Khi chương trình hỏi `Score 1:`, nhập `7.0`, nhấn Enter; tiếp theo `6.5`, rồi `8.0`, mỗi điểm một dòng.

**Dữ liệu nhập:**

```text
7.0
6.5
8.0
```

**Stdout chính xác do chương trình in** (không tính các ký tự bàn phím được terminal tự echo):

```text
Score 1:
Score 2:
Score 3:
Average: 7.17
Result: PASS
```

Trung bình là `(7.0 + 6.5 + 8.0) / 3 = 7.1666...`, được định dạng thành `7.17`. Cả ba điểm đều ít nhất `4.0`, và trung bình ít nhất `5.0`, nên kết luận PASS.

Nếu muốn chạy với input cố định, lưu ba dòng trên vào `sample.txt`, sau đó:

- Linux/macOS hoặc Windows CMD: `java -cp out GradeReport < sample.txt`.
- Windows PowerShell: `Get-Content -LiteralPath sample.txt | java -cp out GradeReport`.

Lệnh `javac` thành công thường không tạo stdout; nội dung dự kiến ở trên đến từ lệnh `java`. Nếu dùng PowerShell hoặc terminal có cài đặt encoding khác, ví dụ này dùng chuỗi ASCII cho các nhãn để tránh khác biệt hiển thị.

## 6. Dùng bảng vết để kiểm tra công thức và điều kiện

Một kỹ thuật đơn giản là viết **bảng trace**: với input cụ thể, tính từng giá trị trung gian trước khi chạy chương trình.

| Input `(s1, s2, s3)` | Trung bình chưa làm tròn | Mọi điểm `>= 4`? | Trung bình `>= 5`? | Kết luận |
| --- | ---: | --- | --- | --- |
| `(7.0, 6.5, 8.0)` | `7.1666...` | Có | Có | PASS |
| `(4, 5, 6)` | `5.0` | Có | Có | PASS |
| `(3.5, 9, 9)` | `7.1666...` | Không | Có | FAIL |
| `(0, 0, 0)` | `0.0` | Không | Không | FAIL |
| `(10, 10, 10)` | `10.0` | Có | Có | PASS |
| `(4, 4, 7)` | `5.0` | Có | Có | PASS |

Bảng này giúp phát hiện lỗi dùng `||` thay vì `&&`, quên chia cho 3 hoặc quên kiểm tra từng môn. Đặc biệt, trường hợp `(3.5, 9, 9)` chứng minh **trung bình cao vẫn có thể FAIL** nếu một môn dưới `4.0`.

### Kiểm tra biên và input không hợp lệ

Dữ liệu sai phải dừng trước phần xử lý:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Điểm `0`, `4`, `5`, `10` | Đều là điểm riêng lẻ hợp lệ |
| Điểm `-0.1` hoặc `10.1` | `out of range` |
| `abc` hoặc dòng rỗng | `invalid` |
| `NaN` hoặc `Infinity` | `out of range` vì không hữu hạn |
| Thiếu dòng điểm tiếp theo khi gặp EOF | `missing` |
| Có nhiều hơn ba dòng | Chương trình mẫu chỉ dùng ba dòng theo hợp đồng; dữ liệu thừa chưa được xử lý |

Ví dụ chạy với **input**:

```text
3.5
9
9
```

**Stdout chính xác:**

```text
Score 1:
Score 2:
Score 3:
Average: 7.17
Result: FAIL
```

Ví dụ với **input** chỉ một dòng `abc`:

```text
abc
```

**Stdout chính xác:**

```text
Score 1:
Error: invalid score1
```

Đây là những đầu vào thử **khác nhau**, mỗi bộ được dùng trong một lần chạy riêng; đừng ghép tất cả vào cùng một lượt nhập nếu muốn so khớp output trên.

## 7. Tách phần tính toán để dễ kiểm thử

Lợi ích của hàm `evaluate` là có thể kiểm thử logic mà không cần giả lập bàn phím hay so khớp lời nhắc. Sau đây là chương trình độc lập khác có thể chạy trên Java 17+, tập trung vào kiểm tra **Process**.

Tạo tệp **`GradeLogicTest.java`**:

```java
public class GradeLogicTest {
    static void check(double a, double b, double c,
                      boolean expectedPass) {
        GradeReport.Result result = GradeReport.evaluate(a, b, c);

        if (result.passed() != expectedPass) {
            throw new AssertionError("wrong decision");
        }

        System.out.println("passed=" + result.passed());
    }

    public static void main(String[] args) {
        check(4, 5, 6, true);
        check(3.5, 9, 9, false);
        check(10, 10, 10, true);
    }
}
```

Lớp `GradeLogicTest` dùng phương thức `evaluate` và record `Result` từ `GradeReport` trong cùng **unnamed package**. Biên dịch đồng thời hai tệp:

```sh
javac -encoding UTF-8 --release 17 -d out GradeReport.java GradeLogicTest.java
java -cp out GradeLogicTest
```

**Stdout chính xác:**

```text
passed=true
passed=false
passed=true
```

Nếu một trường hợp cho quyết định sai, đoạn `throw new AssertionError(...)` làm chương trình kiểm tra thất bại ngay tại lần gọi đó. Đây là một ví dụ kiểm tra tối giản bằng Java core; trong dự án thực tế, có thể dùng JUnit để tổ chức nhiều bài kiểm thử.

**Giới hạn có chủ đích của thiết kế mẫu:** `evaluate` giả định ba điểm đã được `readScore` kiểm tra. Nếu dự án công bố `evaluate` như public API để caller khác có thể truyền số tùy ý, cần đưa validation vào chính hàm này hoặc dùng một kiểu dữ liệu đầu vào có quy tắc bất biến. Mỗi hàm phải nêu rõ tiền điều kiện của mình.

## 8. Phân biệt yêu cầu chức năng và phi chức năng

Ngoài việc đúng công thức, phân tích bài toán có thể cần thêm những ràng buộc:

| Nhóm yêu cầu | Ví dụ với bài tính điểm |
| --- | --- |
| **Chức năng** | Nhập ba điểm; tính trung bình; xác định PASS/FAIL; thông báo input sai |
| **Tính đúng đắn** | So sánh ngưỡng bằng trung bình chưa làm tròn; cả ba điểm phải `>= 4` |
| **Dễ dùng** | Ghi rõ đang yêu cầu nhập điểm số mấy; thông báo lỗi cụ thể |
| **Ổn định** | Kiểm tra EOF, giá trị vô hạn và `NaN`, không ném exception không được xử lý cho input sai thường gặp |
| **Khả năng kiểm thử** | Có `evaluate` riêng, kết quả xác định với cùng input |
| **Khả năng bảo trì** | Tên `readScore`, `evaluate`, `Result` thể hiện trách nhiệm; không lặp công thức ở nhiều nơi |
| **Hiệu năng** | Ba phép đọc và vài phép toán là đủ; chưa cần cấu trúc dữ liệu phức tạp |

Trong bài nhỏ, thời gian xử lý thuật toán là **O(1)** và bộ nhớ phụ trội cho phép tính là **O(1)**, nếu chỉ xét ba điểm cố định. Với dữ liệu nhiều môn, yêu cầu sẽ đổi thành đọc số lượng tùy ý, có thể cần mảng, danh sách hoặc vòng lặp; đó là **một bài toán khác** cần phân tích lại input, điều kiện và output.

## 9. Các lỗi thường gặp khi phân tích bài toán

**Nhầm dữ liệu vào với kết quả cần tính.** Điểm trung bình không phải input nếu đề chỉ cung cấp ba điểm môn học; nó là giá trị được tính trong Process.

**Bỏ qua đơn vị và miền hợp lệ.** Với điểm số, `-1` hay `15` không hợp lệ dù vẫn parse được thành `double`. Với bài tiền tệ hay thời gian, đơn vị còn quan trọng hơn: VND với USD, giây với phút, mét với centimet không thể dùng lẫn.

**Không phân biệt việc parse thành công với dữ liệu hợp lệ.** `Double.parseDouble("20")` thành công, nhưng `20` vẫn ngoài khoảng điểm cho phép.

**Thiếu trường hợp biên.** Một bài toán thường sai ở điểm đúng bằng ngưỡng (`4.0`, `5.0`), giá trị nhỏ nhất/lớn nhất, chuỗi rỗng, input thiếu hoặc số rất lớn.

**Tính toán ngay trong lệnh in.** Nếu viết toàn bộ công thức dài trong `System.out.println(...)`, khó kiểm tra giá trị trung gian và tái sử dụng logic. Tách ra biến hoặc phương thức có tên rõ.

**Chọn kiểu dữ liệu tùy tiện.** Với điểm lẻ cần số thực; với số lượng sản phẩm dùng số nguyên; với tiền tệ chính xác đến đơn vị nhỏ nhất nên cân nhắc số nguyên hoặc `BigDecimal` tùy hợp đồng, không dùng `double` theo thói quen.

**Làm tròn quá sớm.** Nếu chỉ định dạng `%.2f` khi in, quyết định PASS/FAIL vẫn dựa trên giá trị chưa làm tròn. Ví dụ gần ngưỡng có thể được in `5.00` nhưng kết luận FAIL khi giá trị thật còn dưới `5.0`. Nếu người dùng yêu cầu “làm tròn rồi xét”, phải đổi rõ quy tắc xử lý và kiểm thử tương ứng.

**Không mô tả đầu ra lỗi.** Chương trình cần hợp đồng cho cả đầu vào sai. Một stack trace khó hiểu không phải thông báo phù hợp cho mọi chương trình console nhập liệu.

**Trộn Input/Process/Output trong một khối quá dài.** Với bài nhỏ có thể chấp nhận, nhưng khi mở rộng sẽ khó thay terminal thành file/API, khó kiểm thử tính toán và dễ lặp validation.

## 10. Áp dụng IPO cho bài khác

Ví dụ yêu cầu: *Nhập chiều dài và chiều rộng hình chữ nhật; tính diện tích và chu vi.*

| Input | Process | Output |
| --- | --- | --- |
| Hai số dương `length`, `width`, cùng đơn vị (ví dụ mét) | `area = length * width`, `perimeter = 2 * (length + width)` | Diện tích (m²), chu vi (m), hoặc lỗi kích thước không hợp lệ |

Từ bảng này, có thể tạo những test: `(2, 3)` cho diện tích `6`, chu vi `10`; `(0, 3)` là input không hợp lệ nếu hợp đồng yêu cầu hai cạnh **lớn hơn 0**; `(-2, 3)` cũng không hợp lệ.

Nếu người dùng nhập kích thước bằng centimet nhưng muốn diện tích m², phải thêm bước **đổi đơn vị** trong Process. Chỉ đổi tên biến hoặc nối chữ `m²` ở Output sẽ không khiến kết quả tự đúng.

## 11. Checklist trước khi bắt đầu code

1. Tôi có thể mô tả **mỗi input** bằng tên, kiểu, đơn vị, nguồn và miền hợp lệ không?
2. Có quy tắc nào còn mơ hồ về làm tròn, ngưỡng, dữ liệu thiếu hoặc dữ liệu thừa không?
3. Tôi đã viết **công thức, điều kiện, thứ tự xử lý** thành giả mã hay sơ đồ rõ ràng chưa?
4. Tôi có chỉ rõ **output thành công và output khi lỗi** không?
5. Tôi đã thử tính tay ít nhất một trường hợp thông thường, một trường hợp sát ngưỡng và một trường hợp sai dữ liệu chưa?
6. Có thể tách **đọc**, **xử lý** và **in/return** thành các khối hoặc phương thức có trách nhiệm rõ ràng không?
7. Tôi đã biên dịch bằng `javac`, chạy bằng `java` và đối chiếu output thực với kết quả dự kiến chưa?

**Ghi nhớ:** Trước khi chọn cú pháp Java, hãy chuyển yêu cầu thành **Input có hợp đồng rõ ràng → Process có công thức và quy tắc kiểm tra → Output có thể kiểm chứng**. Phân tích tốt giúp code ngắn hơn, dễ sửa hơn và tránh nhiều lỗi logic ngay từ đầu.
