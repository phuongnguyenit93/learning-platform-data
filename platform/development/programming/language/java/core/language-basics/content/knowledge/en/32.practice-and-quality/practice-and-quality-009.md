# Thực hành menu console với kiểm tra đầu vào (Java 17+)

## 1. Mục tiêu và yêu cầu bài toán

Một **menu console** là chương trình hiển thị danh sách lựa chọn, nhận thao tác của người dùng rồi thực hiện hành động tương ứng. Menu thường cần **lặp lại** cho đến khi người dùng chủ động chọn thoát. Nếu chỉ đọc lựa chọn bằng `nextInt()` rồi dùng `switch`, chương trình dễ gặp vấn đề khi người dùng nhập chữ, số ngoài phạm vi, chuỗi rỗng hoặc kết thúc luồng nhập (*EOF*).

Bài thực hành này xây dựng **menu quản lý tổng điểm** trên Java 17+, với các lựa chọn:

| Lựa chọn | Hành động | Dữ liệu thêm |
| --- | --- | --- |
| `1` | Thêm điểm vào tổng hiện tại | Nhập một số nguyên từ `1` đến `1000` |
| `2` | Xem tổng điểm hiện tại | Không |
| `3` | Đặt tổng điểm về `0` | Không |
| `0` | Thoát chương trình | Không |

**Hợp đồng đầu vào:**

- Lựa chọn menu phải là **số nguyên từ 0 đến 3**.
- Số điểm thêm vào phải là **số nguyên từ 1 đến 1000**; không nhận `0`, số âm hoặc phân số.
- Nếu nhập ký tự không phải số nguyên (`abc`, `1.5`, dòng rỗng, số nguyên vượt miền `int`), chương trình **báo lỗi và hỏi lại trường đang nhập**, không tự thoát hoặc đổi tổng.
- Nếu nhập số nguyên ngoài phạm vi, chương trình báo đúng khoảng hợp lệ và hỏi lại.
- Nếu luồng đầu vào kết thúc trước khi có lựa chọn hợp lệ, chương trình thông báo `Input ended.` rồi kết thúc có kiểm soát.
- Tổng điểm khởi đầu là `0` và chỉ tăng khi một lượt **thêm điểm hợp lệ** được chấp nhận.

Đây là menu minh họa để luyện vòng lặp, lựa chọn, kiểm tra dữ liệu và quản lý trạng thái, không phải hệ thống tích điểm thực tế.

## 2. Phân tích Input – Process – Output

| Phần | Nội dung | Cách dùng Java |
| --- | --- | --- |
| Input | Lựa chọn `0`–`3` | `Scanner.nextLine()`, `Integer.parseInt()` |
| Input | Số điểm thêm `1`–`1000` nếu chọn `1` | Cùng hàm đọc và xác thực đầu vào |
| Process | Lặp lại menu cho tới khi thoát | `while (true)` |
| Process | Chuyển lựa chọn thành hành động | `switch` với cú pháp `case ... ->` |
| Process | Cộng dồn hoặc đặt lại `total` | `long total` được khai báo **ngoài** vòng lặp |
| Output | Menu, lời nhắc, lỗi, điểm vừa thêm, tổng và lời chào thoát | `System.out.println()` |

Chọn `long` cho tổng vì nhiều lần cộng có thể vượt miền `int`; điểm mỗi lượt được lưu dưới dạng `int` vì giới hạn tối đa chỉ `1000`. Bài này không đặt giới hạn tổng số lượt; trong chương trình chạy cực lâu, vẫn cần xem xét giới hạn tổng hoặc `Math.addExact()` để ngăn tràn `long`. Với một phiên console học tập thông thường, đây không phải vấn đề thực tế.

### Sơ đồ logic

```text
Khởi tạo total = 0
        |
        v
Hiển thị menu
        |
        v
Đọc và kiểm tra lựa chọn
        |
        +-- EOF ------------------------> Thông báo và kết thúc
        |
        +-- Không đúng kiểu/khoảng ----> Báo lỗi, hỏi lại lựa chọn
        |
        v
switch(choice)
        |
        +-- 1: hỏi điểm -- sai --> báo lỗi, hỏi lại điểm
        |              |
        |              +-- hợp lệ --> cộng total, thông báo
        |              |
        |              +-- EOF -------> thông báo và kết thúc
        |
        +-- 2: in tổng hiện tại
        |
        +-- 3: đặt tổng về 0
        |
        +-- 0: chào và kết thúc
        |
        v
Quay lại menu sau hành động 1, 2 hoặc 3
```

Điểm then chốt là **vòng lặp nhập lại ở bên trong từng lời nhắc** và **vòng lặp menu ở bên ngoài** có hai trách nhiệm khác nhau. Dữ liệu sai ở lời nhắc điểm không nên tự đưa người dùng về menu, và dữ liệu sai ở lời nhắc menu không được làm thay đổi tổng.

## 3. Code Java 17+ đầy đủ: MenuConsoleApp.java

Tạo một tệp tên **`MenuConsoleApp.java`** với đúng nội dung sau:

```java
import java.util.Scanner;

public final class MenuConsoleApp {
    private MenuConsoleApp() {
    }

    /**
     * Đọc một số nguyên trong khoảng cho phép.
     * Trả về null nếu nguồn đầu vào đã kết thúc.
     */
    private static Integer readIntInRange(
            Scanner scanner, String prompt, int min, int max) {

        while (true) {
            System.out.println(prompt);

            if (!scanner.hasNextLine()) {
                return null;
            }

            String text = scanner.nextLine().strip();
            final int value;

            try {
                value = Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                System.out.println("Error: enter an integer.");
                continue;
            }

            if (value < min || value > max) {
                System.out.println("Error: value must be from "
                        + min + " to " + max + ".");
                continue;
            }

            return value;
        }
    }

    public static void main(String[] args) {
        long total = 0L;

        try (Scanner scanner = new Scanner(System.in)) {
            while (true) {
                System.out.println("=== MENU ===");
                System.out.println("1. Add points");
                System.out.println("2. View total");
                System.out.println("3. Reset total");
                System.out.println("0. Exit");

                Integer choice = readIntInRange(
                        scanner, "Choice (0-3):", 0, 3);

                if (choice == null) {
                    System.out.println("Input ended.");
                    return;
                }

                switch (choice) {
                    case 1 -> {
                        Integer points = readIntInRange(
                                scanner, "Points (1-1000):", 1, 1000);

                        if (points == null) {
                            System.out.println("Input ended.");
                            return;
                        }

                        total += points;
                        System.out.println("Added: " + points);
                    }
                    case 2 -> System.out.println("Total: " + total);
                    case 3 -> {
                        total = 0L;
                        System.out.println("Total reset.");
                    }
                    case 0 -> {
                        System.out.println("Goodbye.");
                        return;
                    }
                    default -> throw new AssertionError(
                            "Unexpected validated menu choice");
                }
            }
        }
    }
}
```

### Giải thích theo từng phần

**`readIntInRange()` — một chỗ duy nhất để kiểm tra kiểu và phạm vi.** Phương thức in lời nhắc, đọc trọn một dòng với `nextLine()`, bỏ khoảng trắng đầu/cuối bằng `strip()`, rồi chuyển thành `int` với `Integer.parseInt()`. Nếu chuyển đổi thất bại, `catch (NumberFormatException)` báo lỗi và dùng `continue` để hỏi lại **chính câu hỏi đang nhập**. Nếu số nằm ngoài `[min, max]`, cũng báo lỗi và hỏi lại.

**`Integer` thay vì `int` cho kết quả đọc.** Phương thức cần biểu diễn hai tình trạng riêng biệt: đọc được một số hợp lệ, hoặc **EOF trước khi có số**. `Integer` có thể là `null` khi EOF; riêng lựa chọn `0` vẫn là một **số hợp lệ có ý nghĩa thoát**. Vì vậy không dùng `0` thay cho EOF. Sau khi xác nhận `choice != null`, `switch (choice)` có thể unbox sang `int` an toàn.

**`while (true)` ngoài cùng — tiếp tục hiển thị menu.** Sau lựa chọn 1, 2 hoặc 3, chương trình kết thúc nhánh `switch` rồi quay về đầu vòng lặp. Lựa chọn 0 gọi `return` để kết thúc `main`. Khối `try-with-resources` đóng scanner khi rời khối.

**`switch (choice)` — thực hiện đúng một hành động.** Cú pháp nhánh có mũi tên `case 1 ->` được Java 17 hỗ trợ và không có hiện tượng *fall-through* như dạng `case 1:` cũ nếu quên `break`. Với những nhánh có nhiều lệnh, dùng khối `{ ... }` để khai báo biến và xử lý.

**`total` ngoài vòng lặp — giữ trạng thái.** Nếu đặt `long total = 0L;` bên trong `while`, tổng sẽ trở về 0 mỗi khi menu hiện lại. Chỉ nhánh 1 (nhập điểm hợp lệ) tăng tổng; nhánh 3 chủ động đặt lại.

**`default` là chốt kiểm tra lập trình.** Vì `readIntInRange` đã giới hạn lựa chọn từ 0 đến 3, đây là nhánh không thể đến theo luồng bình thường. Nếu sau này ai đó sửa menu hoặc bộ kiểm tra không đồng bộ, `AssertionError` giúp phát hiện lỗi thiết kế thay vì im lặng bỏ qua.

## 4. Biên dịch và chạy bằng CLI

Dùng **JDK 17+** trong thư mục có file `MenuConsoleApp.java`. Tạo thư mục `out` một lần nếu chưa tồn tại:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out MenuConsoleApp.java
java -cp out MenuConsoleApp
```

Các lệnh `javac` và `java` dùng được trên Windows PowerShell, Windows CMD, Linux và macOS. Nếu biên dịch thành công, `javac` thường không in nội dung nào. `-d out` chỉ định thư mục chứa `MenuConsoleApp.class`; `-cp out` bảo JVM tìm lớp trong thư mục đó. Không cần viết `.class` khi gọi `java`.

Chương trình sẽ hiển thị menu và chờ người dùng nhập lựa chọn. Sau mỗi số, nhấn Enter. Bạn cũng có thể lưu dãy input vào `sample.txt` để tái hiện đúng stdout:

- **Linux/macOS hoặc Windows CMD:** `java -cp out MenuConsoleApp < sample.txt`.
- **Windows PowerShell:** `Get-Content -LiteralPath sample.txt | java -cp out MenuConsoleApp`.

Khi chạy tương tác, terminal có thể tự hiển thị lại các ký tự bàn phím người dùng gõ. Phần đó **không thuộc stdout** do các lệnh `println()` của Java tạo ra; ví dụ dưới đây chỉ liệt kê stdout của chương trình.

## 5. Kiểm thử luồng menu thông thường

Tạo `sample.txt` với sáu dòng **đầu vào**:

```text
1
7
2
3
2
0
```

Ý nghĩa: thêm 7 điểm, xem tổng, đặt lại tổng, xem tổng một lần nữa, thoát.

**Stdout chính xác**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Points (1-1000):
Added: 7
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total: 7
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total reset.
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total: 0
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Goodbye.
```

Hãy đối chiếu từng lượt:

1. Lựa chọn `1` khiến chương trình hỏi thêm `Points (1-1000):`, nhận `7`, cộng `total = 0 + 7`.
2. Lựa chọn `2` **không hỏi điểm**; chỉ in `Total: 7`.
3. Lựa chọn `3` đặt `total = 0`, xác nhận bằng `Total reset.`.
4. Lựa chọn `2` lần nữa in `Total: 0`, chứng minh giá trị đã được đặt lại.
5. Lựa chọn `0` in `Goodbye.`, sau đó rời chương trình; không hiển thị menu lần thứ sáu.

## 6. Kiểm thử đầu vào không hợp lệ

Tạo một file đầu vào khác với ba dòng:

```text
abc
9
0
```

**Stdout chính xác**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Error: enter an integer.
Choice (0-3):
Error: value must be from 0 to 3.
Choice (0-3):
Goodbye.
```

Giải thích:

- `abc` không thể chuyển thành `int`; `Integer.parseInt("abc")` ném `NumberFormatException`. Chương trình **bắt lỗi trong helper** và hỏi lại lựa chọn.
- `9` là `int` hợp lệ về kiểu nhưng nằm ngoài menu 0–3; chương trình báo lỗi **phạm vi**, không coi đó là lựa chọn bí mật.
- `0` hợp lệ và dẫn tới nhánh thoát.
- Trong hai lần nhập sai, **menu không hiển thị lại toàn bộ** vì lỗi được xử lý ở vòng lặp nhập lựa chọn bên trong `readIntInRange()`, đúng với mục đích giữ người dùng ở cùng trường nhập.

Tương tự, nếu chọn 1 nhưng nhập `0`, `-1`, `1001`, `1.5`, chuỗi rỗng hoặc `999999999999999999999` vào lời nhắc điểm, chương trình tiếp tục hỏi lại cho đến khi nhận số nguyên từ 1 đến 1000 hoặc gặp EOF. Những trường hợp này **không cộng vào tổng**.

**Quan trọng:** lỗi định dạng và lỗi phạm vi khác nhau. `"1.5"` là văn bản không parse được bằng `Integer.parseInt`, trong khi `1001` parse thành công nhưng vi phạm điều kiện bài toán.

## 7. Xử lý EOF thay vì chờ hoặc phát sinh lỗi

EOF (*end of file*) có thể xảy ra khi file chuyển vào chương trình đã hết dòng, pipe bị đóng hoặc người dùng kết thúc nhập theo cách terminal hỗ trợ. EOF **khác** lựa chọn 0:

- **Chọn 0:** người dùng yêu cầu thoát; chương trình in `Goodbye.`.
- **Gặp EOF:** không còn dữ liệu để đọc; helper trả `null`, chương trình in `Input ended.`.

Ví dụ đầu vào trống (file `empty.txt` không có dòng nào) cho **stdout chính xác**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Input ended.
```

Nếu input chỉ có dòng `1` và sau đó EOF, chương trình in menu, nhận lựa chọn 1, in `Points (1-1000):`, rồi `Input ended.`. Nó không cộng điểm và không tiếp tục lặp vô hạn.

Phương thức `hasNextLine()` kiểm tra **còn dòng để đọc**, không kiểm tra dòng tiếp theo có phải số nguyên hay không. Đó là lý do phải thực hiện cả hai bước: `hasNextLine()` cho EOF và `Integer.parseInt()` cho tính hợp lệ của số.

Trong console tương tác, `hasNextLine()` có thể **chờ input** khi luồng chưa gửi dòng và chưa kết thúc. Việc chương trình đang chờ không đồng nghĩa với vòng lặp vô hạn; hãy phân biệt nó với trường hợp code đọc đi đọc lại cùng một token sai mà không tiêu thụ.

## 8. Vì sao đọc cả dòng rồi parse thay vì gọi `nextInt()`?

Một cách viết dễ gặp là:

```java
int choice = scanner.nextInt();
```

Nếu người dùng nhập `abc`, lời gọi này có thể ném `InputMismatchException`. Ngoài ra, khi trộn `nextInt()` với `nextLine()`, ký tự kết thúc dòng còn lại có thể khiến `nextLine()` kế tiếp trả chuỗi rỗng.

Cách của bài này là:

```java
String text = scanner.nextLine().strip();
int choice = Integer.parseInt(text);
```

Đoạn trên chỉ minh họa **hai câu lệnh**, với giả định biến `scanner` đã tồn tại và input đúng định dạng; trong ví dụ đầy đủ, thao tác parse nằm trong `try/catch` để không làm chương trình dừng khi sai.

Ưu điểm của đọc cả dòng:

- Mỗi lượt nhập tương ứng **một dòng rõ ràng**, không để lại newline của cùng dòng.
- Dễ phân biệt **EOF**, chuỗi rỗng, dữ liệu chứa khoảng trắng, dữ liệu không phải số và giá trị ngoài miền.
- Có thể in thông báo và hỏi lại một cách ổn định.
- Không cần tạo nhiều đối tượng `Scanner` cho cùng một `System.in`.

Nếu định dạng đầu vào thật sự là nhiều số trên cùng một dòng, đọc từng token có thể thuận tiện hơn. Không có quy tắc rằng `nextInt()` luôn sai; vấn đề là chọn cách đọc phù hợp với cấu trúc dữ liệu và xử lý lỗi đúng.

## 9. Phân biệt các câu lệnh điều khiển vòng lặp

Trong menu, rất dễ nhầm `continue`, `break` và `return`.

| Câu lệnh | Ảnh hưởng | Áp dụng trong bài |
| --- | --- | --- |
| `continue` | Bỏ phần còn lại của **lượt lặp hiện tại**, chuyển sang lượt kế tiếp của vòng lặp gần nhất | Khi nhập sai trong `readIntInRange()`, tiếp tục **hỏi lại trường đó** |
| `break` | Thoát khỏi vòng lặp hoặc `switch` gần nhất theo dạng cú pháp tương ứng | Có thể dùng cho vòng menu, nhưng ví dụ dùng `return` khi chọn 0 |
| `return` | Kết thúc phương thức đang thực thi | Trong `main`, thoát hẳn chương trình; trong helper, trả giá trị hoặc `null` |
| `case ... ->` | Nhánh `switch` có cú pháp mũi tên, không chạy xuyên sang nhánh khác | Hành động 1, 2, 3, 0 độc lập |

**Lưu ý:** Nếu dùng dạng `switch (choice) { case 0: break; ... }`, `break` trong `case 0:` chỉ thoát `switch`, **không tự thoát vòng `while` bao ngoài**. Chương trình có thể hiển thị menu lại thay vì kết thúc. Cần cờ điều khiển vòng, `break` có nhãn trong trường hợp phù hợp, hoặc `return` như bài mẫu.

Trong Java 17, `switch` dạng arrow `case 1 -> ...` có thể dùng như một switch statement. Khi có nhiều lệnh trong nhánh, đặt vào `{ ... }`. Không cần `break` cuối mỗi nhánh dạng arrow.

## 10. Các trường hợp kiểm thử nên có

| Input/đường đi | Kết quả cần xác minh |
| --- | --- |
| `0` ngay tại menu đầu tiên | In `Goodbye.`, không hỏi số điểm |
| `1, 7, 2, 0` (mỗi giá trị một dòng) | In `Added: 7`, sau đó `Total: 7`, rồi thoát |
| `1, 7, 3, 2, 0` | Tổng cuối là 0 sau khi reset |
| `abc, 0` | Báo lỗi định dạng, hỏi lại, sau đó thoát |
| `-1, 4, 0` | Báo lỗi phạm vi hai lần rồi thoát |
| `1, abc, 5, 2, 0` | Không thêm `abc`; thêm 5 điểm và xem `Total: 5` |
| `1, 1001, 1000, 2, 0` | Báo lỗi cho 1001, chấp nhận biên 1000, tổng 1000 |
| `1, 0, 1, 2, 0` | Điểm 0 sai; sau đó thêm điểm 1 |
| Một file rỗng | In `Input ended.` và kết thúc |
| Chỉ nhập `1` rồi EOF | Đã vào nhánh thêm điểm nhưng kết thúc an toàn vì không có điểm |
| Dòng có khoảng trắng ` 2 ` | `strip()` giúp parse thành lựa chọn 2 |
| Số ngoài miền `int` | `NumberFormatException` được bắt, hỏi lại mà không crash |

**Nguyên tắc kiểm thử:** Mỗi kịch bản dùng **một lần chạy riêng** và đưa các mục trong cột input thành **các dòng liên tiếp**, không phải gõ dấu phẩy giữa các số. Nếu một trường hợp có lỗi, phải kiểm tra cả việc trạng thái không bị thay đổi sai, không chỉ kiểm tra có thông báo lỗi hay không.

## 11. Những lỗi lập trình phổ biến và cách tránh

**(a) Đặt `total` trong vòng lặp menu.** Nếu mỗi lần hiện menu đều chạy `long total = 0;`, điểm sẽ bị mất. Khởi tạo tổng **một lần** trước vòng lặp.

**(b) Không tiêu thụ dữ liệu sai.** Với `Scanner.nextInt()`, một token sai có thể vẫn còn trong luồng; nếu cứ `hasNextInt()` mà không bỏ token, vòng lặp sẽ đứng tại dữ liệu lỗi. Cách đọc `nextLine()` của bài mẫu **tiêu thụ cả dòng** trước khi parse nên mỗi lượt kiểm tra tiến tới dòng tiếp theo.

**(c) Dùng `if` liên tiếp mà thiếu trường hợp thoát.** Menu càng nhiều lựa chọn càng khó kiểm soát nếu mọi hành động chỉ là các `if` độc lập. `switch` làm rõ mỗi lựa chọn tương ứng một hành động, còn vòng ngoài quản lý việc hiển thị lại.

**(d) Bắt mọi `Exception` rồi bỏ qua.** Việc che mọi lỗi làm khó phân biệt dữ liệu sai với bug lập trình. `readIntInRange()` chỉ bắt `NumberFormatException`, tức lỗi được dự kiến khi parse đầu vào.

**(e) Không kiểm tra EOF.** Gọi `scanner.nextLine()` khi không còn dòng có thể ném `NoSuchElementException`. Dùng `hasNextLine()` rồi cho caller biết EOF bằng giá trị trả về có ý nghĩa.

**(f) Nhầm số nguyên với số thực.** `1.0` có giá trị số học bằng 1 nhưng không phải chuỗi số nguyên theo cú pháp `Integer.parseInt()`; muốn chấp nhận số thực phải có quy tắc chuyển kiểu riêng, không âm thầm làm tròn.

**(g) Sai ranh giới.** Lựa chọn `0` và `3` đều hợp lệ; `-1` và `4` không hợp lệ. Số điểm `1` và `1000` hợp lệ; `0` và `1001` không. Kiểm thử đúng các mốc này tránh lỗi dùng `<` thay vì `<=`.

**(h) Tạo nhiều Scanner cho `System.in`.** Các scanner có bộ đệm riêng và có thể cạnh tranh cùng luồng nhập; nên dùng một scanner xuyên suốt phiên tương tác. Việc đóng `Scanner(System.in)` sẽ đóng cả luồng đầu vào bên dưới; ví dụ đóng khi kết thúc `main`, phù hợp với bài thực hành đơn lẻ.

**(i) Để menu lặp mãi mà không có đường thoát.** `while (true)` chỉ phù hợp khi có một hoặc nhiều con đường thoát xác định: lựa chọn 0, EOF hoặc lỗi nghiêm trọng được xử lý bằng cách kết thúc an toàn.

## 12. Hướng cải tiến sau khi chạy đúng

Khi muốn mở rộng menu, nên giữ nguyên các nguyên tắc trước:

1. **Tách từng hành động thành một phương thức** nếu nhánh bắt đầu dài. Ví dụ `showTotal(total)` hoặc `addPoints(scanner, total)` cần hợp đồng rõ: có thay đổi trạng thái không, xử lý EOF thế nào.
2. **Giữ logic và nhập xuất tách biệt** khi ứng dụng lớn lên. Phép cộng điểm có thể trở thành hàm thuần để kiểm thử mà không cần Scanner.
3. **Thêm tùy chọn xem lịch sử cộng điểm** nếu bài yêu cầu lưu các lần thay đổi; khi đó cần danh sách hoặc kiểu bản ghi, không chỉ biến tổng.
4. **Áp dụng giới hạn tổng hoặc `Math.addExact()`** nếu số lượt cộng không được kiểm soát và sự chính xác của số lớn là yêu cầu nghiêm ngặt.
5. **Xác định ngôn ngữ/định dạng thông báo** và tài liệu cho người dùng nếu menu phục vụ nhiều đối tượng.
6. **Viết test cho xử lý input** với các chuỗi cố định qua `new Scanner(String)` hoặc chạy chương trình với file/pipe, so khớp stdout. Với trường hợp lớn, có thể dùng JUnit nhưng không bắt buộc cho Java core.

Đừng mở rộng quá sớm: đầu tiên hãy bảo đảm menu đơn giản **hiển thị lại đúng, kiểm tra input đúng, không làm thay đổi tổng khi nhập sai và thoát có kiểm soát**.

## 13. Checklist tổng kết

Trước khi coi chương trình hoàn thành, hãy tự xác nhận:

- Menu có các lựa chọn rõ ràng `0`–`3`, và chỉ số trong `switch` khớp lời nhắc?
- `while` có đường thoát `0` và EOF?
- Nhập chuỗi, dòng rỗng, số vượt phạm vi hoặc số vượt kiểu `int` không làm chương trình crash?
- Dữ liệu sai có dẫn tới **hỏi lại đúng trường**, không tự thêm điểm hay đổi tổng?
- Sau lựa chọn 1, 2, 3, menu có được hiển thị lại?
- `total` có giữ nguyên qua các lượt, trừ khi được cộng hoặc đặt lại có chủ đích?
- `0` để thoát có khác `null` do EOF?
- Chương trình dùng một `Scanner` có vòng đời phù hợp, tránh trộn `nextInt()` và `nextLine()` gây đọc nhầm newline?
- Đã chạy `javac`/ `java` và đối chiếu kịch bản hợp lệ, dữ liệu sai và EOF chưa?

**Ghi nhớ:** Một menu console chắc chắn cần **vòng lặp để duy trì tương tác, `switch` để phân nhánh hành động, kiểm tra đầu vào ở ngay ranh giới nhập liệu và đường thoát rõ ràng**. Viết đúng bốn phần này giúp bài tập hoạt động dự đoán được ngay cả khi người dùng nhập sai.
