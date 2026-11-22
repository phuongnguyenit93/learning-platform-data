# Xử lý phần xuống dòng còn lại sau khi đọc số (Java 17+)

## 1. Hiện tượng thường gặp

Khi dùng `Scanner` đọc dữ liệu console, một lỗi rất hay gặp là gọi `nextInt()` hoặc `nextDouble()` rồi gọi ngay `nextLine()` để đọc họ tên, ghi chú hoặc câu văn. Kết quả đầu tiên của `nextLine()` có thể là **chuỗi rỗng** hoặc chỉ gồm dấu cách, dù người dùng đã dự định nhập một dòng văn bản khác.

Ví dụ, đầu vào:

```text
21
Nguyen Van An
```

Nếu code là:

```java
int age = scanner.nextInt();
String name = scanner.nextLine();
```

thì `age` là `21`, nhưng `name` là `""`, vì `nextLine()` đang đọc **phần còn lại của dòng chứa số 21**, không phải dòng `Nguyen Van An`.

Vấn đề không phải Java tự tạo một dòng rỗng. Nó xuất phát từ việc kết hợp **đọc token** với **đọc dòng** trên cùng đối tượng `Scanner`.

## 2. Cơ chế: `nextInt()` và `nextLine()` đọc khác nhau

`Scanner` có hai kiểu đọc thường dùng:

| Phương thức | Đơn vị đọc | Điều xảy ra với ký tự kết thúc dòng |
| --- | --- | --- |
| `next()` | Một token, mặc định được phân cách bằng khoảng trắng | Không đọc toàn bộ phần còn lại của dòng |
| `nextInt()`, `nextLong()` | Một token số nguyên | Parse token, không tự tiêu thụ phần còn lại của dòng |
| `nextDouble()`, `nextFloat()` | Một token số thực | Parse token, không tự tiêu thụ phần còn lại của dòng |
| `nextLine()` | Phần còn lại của dòng hiện tại | Đọc tới hết dòng, bỏ ký tự kết thúc dòng khỏi chuỗi trả về |
| `hasNextLine()` | Kiểm tra có thể đọc dòng tiếp hay không | Không tiêu thụ dòng |

Mặc định, `Scanner` nhận khoảng trắng, tab, ký tự xuống dòng là các dấu phân cách token. Nhưng việc **tách token** không đồng nghĩa với việc **đã đi qua hết dòng**.

Với input `21\nNguyen Van An\n` (trong đó `\n` đại diện cho một ký tự xuống dòng), có thể hình dung:

```text
Ban đầu:
21↵
Nguyen Van An↵
^

Sau nextInt():
21↵
Nguyen Van An↵
  ^
  (phần kết thúc dòng 21 vẫn cần được xử lý)

Sau nextLine():
21↵
Nguyen Van An↵
   ^
   (đã chuyển sang dòng kế tiếp, nhưng kết quả vừa trả là "")

Sau nextLine() tiếp:
21↵
Nguyen Van An↵
             ^
             (lấy được "Nguyen Van An")
```

Sơ đồ thể hiện trình tự logic, không phải vị trí byte chính xác của bộ đệm nội bộ. Đặc biệt, nếu input là `21   \n` có **ba dấu cách** sau số, `nextLine()` đầu tiên có thể trả về `"   "`, chứ không phải `""`. Vì vậy cách diễn đạt chính xác là **đọc phần dư của dòng**, đôi khi phần dư đó rỗng.

## 3. Chương trình tái hiện lỗi với kết quả cố định

Tạo file **`LeftoverDemo.java`**:

```java
import java.util.Scanner;

public class LeftoverDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("21\nNguyen Van An\n")) {
            int age = scanner.nextInt();
            String firstLine = scanner.nextLine();
            String secondLine = scanner.nextLine();

            System.out.println("age=" + age);
            System.out.println("firstLine=[" + firstLine + "]");
            System.out.println("secondLine=[" + secondLine + "]");
        }
    }
}
```

Để biên dịch và chạy bằng **JDK 17+** trong thư mục chứa file (PowerShell, CMD, bash), tạo thư mục output nếu chưa có:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out LeftoverDemo.java
java -cp out LeftoverDemo
```

**Stdout chính xác:**

```text
age=21
firstLine=[]
secondLine=[Nguyen Van An]
```

`new Scanner(String)` được dùng để mô phỏng console, giúp tái hiện đầu vào không phụ thuộc người đang gõ. Khi thay bằng `new Scanner(System.in)`, quy tắc đọc token và dòng vẫn như vậy.

Nếu chương trình chỉ gọi một lần `nextLine()` sau `nextInt()`, nó sẽ nhận `firstLine=[]` và dễ gây hiểu nhầm rằng Java “bỏ qua” họ tên. Thực tế, họ tên vẫn nằm ở dòng kế tiếp, đang chờ được đọc.

## 4. Cách sửa A: tiêu thụ phần dư của dòng sau khi đọc số

Khi định dạng đầu vào quy định **số ở một dòng riêng**, tiếp theo là **văn bản ở dòng riêng**, có thể thêm một lần `nextLine()` để **bỏ phần dư** của dòng chứa số:

```java
int age = scanner.nextInt();
scanner.nextLine();             // bỏ phần còn lại của dòng chứa tuổi
String name = scanner.nextLine();
```

Dòng `scanner.nextLine();` ở giữa không phải để nhận tên; nó chỉ hoàn tất dòng đã chứa số.

### Chương trình hoàn chỉnh đọc từ console

Tạo file **`ConsumeRemainderDemo.java`**:

```java
import java.util.Scanner;

public class ConsumeRemainderDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            System.out.println("Enter age:");

            if (!scanner.hasNextInt()) {
                System.out.println("Error: expected an integer age");
                return;
            }

            int age = scanner.nextInt();

            if (!scanner.hasNextLine()) {
                System.out.println("Error: expected a separate name line");
                return;
            }
            scanner.nextLine(); // consume rest of age line

            System.out.println("Enter full name:");
            if (!scanner.hasNextLine()) {
                System.out.println("Error: name line missing");
                return;
            }
            String name = scanner.nextLine();

            System.out.println("age=" + age);
            System.out.println("name=" + name);
        }
    }
}
```

Biên dịch:

```sh
javac -encoding UTF-8 --release 17 -d out ConsumeRemainderDemo.java
java -cp out ConsumeRemainderDemo
```

Với đầu vào **hai dòng riêng**:

```text
21
Nguyen Van An
```

**Stdout của chính chương trình** (không tính ký tự terminal tự echo khi gõ phím):

```text
Enter age:
Enter full name:
age=21
name=Nguyen Van An
```

Để chạy lặp lại với đầu vào cố định, lưu đúng hai dòng trên vào `sample.txt`, rồi dùng:

- Bash hoặc Windows CMD: `java -cp out ConsumeRemainderDemo < sample.txt`.
- Windows PowerShell: `Get-Content -LiteralPath sample.txt | java -cp out ConsumeRemainderDemo`.

Ví dụ giả định tuổi hợp lệ về mặt số nguyên. Để kiểm tra giới hạn tuổi (ví dụ 0–120), cần một bước validation nghiệp vụ riêng sau khi đọc số.

**Điểm quan trọng:** Không thêm `nextLine()` bỏ phần dư một cách máy móc nếu thông tin bạn cần vẫn **nằm trên chính dòng chứa số**. Việc bỏ phần dư khi đó sẽ làm mất dữ liệu thật.

## 5. Khi số và văn bản ở cùng một dòng: giữ lại phần dư

Giả sử định dạng là:

```text
21 Nguyen Van An
```

Ở đây, sau `nextInt()`, phần dư của dòng là `" Nguyen Van An"`, tức chính là họ tên bạn cần. Nếu gọi `scanner.nextLine();` chỉ để vứt kết quả, bạn sẽ mất tên.

Thay vào đó, hãy **lưu phần dư** rồi xử lý dấu cách đầu dòng.

Tạo **`SameLineDemo.java`**:

```java
import java.util.Scanner;

public class SameLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("21 Nguyen Van An\n")) {
            int age = scanner.nextInt();
            String name = scanner.nextLine().stripLeading();

            System.out.println("age=" + age);
            System.out.println("name=" + name);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out SameLineDemo.java
java -cp out SameLineDemo
```

**Stdout chính xác:**

```text
age=21
name=Nguyen Van An
```

`stripLeading()` (có từ Java 11) bỏ khoảng trắng ở đầu chuỗi nhưng giữ nguyên phần còn lại, phù hợp khi dấu cách đầu là ranh giới sau số. `trim()` hoặc `strip()` có thể dùng khi đầu vào được phép xóa khoảng trắng **cả hai đầu**. Cần chọn theo hợp đồng input, nhất là nếu khoảng trắng cuối dòng có ý nghĩa.

Nếu không có tên sau số, `name` có thể rỗng; khi đó cần xử lý lỗi dữ liệu thiếu, không tự giả định rằng còn một dòng kế tiếp.

## 6. Cách sửa B: chỉ dùng `nextLine()`, rồi parse số

Đối với chương trình console nhập **mỗi trường trên một dòng**, cách nhất quán và thường dễ kiểm soát nhất là đọc toàn bộ từng dòng, sau đó tự chuyển sang kiểu số:

```java
String ageText = scanner.nextLine();
int age = Integer.parseInt(ageText.strip());
String name = scanner.nextLine();
```

Cách này không trộn đọc token với đọc dòng nên không còn lỗi phần dư do `nextInt()`/ `nextLine()`. Đổi lại, `Integer.parseInt` ném `NumberFormatException` nếu dòng không biểu diễn số nguyên hợp lệ.

### Ví dụ đầy đủ: xử lý input thiếu hoặc sai

Tạo file **`LineFirstDemo.java`**:

```java
import java.util.Scanner;

public class LineFirstDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            System.out.println("Enter age:");
            if (!scanner.hasNextLine()) {
                System.out.println("Error: age line missing");
                return;
            }

            String ageLine = scanner.nextLine();
            final int age;
            try {
                age = Integer.parseInt(ageLine.strip());
            } catch (NumberFormatException ex) {
                System.out.println("Error: age must be an integer");
                return;
            }

            if (age < 0 || age > 120) {
                System.out.println("Error: age out of range");
                return;
            }

            System.out.println("Enter full name:");
            if (!scanner.hasNextLine()) {
                System.out.println("Error: name line missing");
                return;
            }

            String name = scanner.nextLine().strip();
            if (name.isEmpty()) {
                System.out.println("Error: name is empty");
                return;
            }

            System.out.println("age=" + age);
            System.out.println("name=" + name);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out LineFirstDemo.java
java -cp out LineFirstDemo
```

Với input:

```text
21
Nguyen Van An
```

**Stdout chính xác:**

```text
Enter age:
Enter full name:
age=21
name=Nguyen Van An
```

Với dòng tuổi là `abc`, chương trình in:

```text
Enter age:
Error: age must be an integer
```

Nếu dòng tuổi hợp lệ nhưng chưa có dòng tên vì input đã hết (EOF), chương trình in `Error: name line missing` sau khi in hai lời nhắc. `hasNextLine()` giúp tránh `NoSuchElementException` khi nguồn input không còn dòng để đọc.

Cách dùng `nextLine()` rồi `Integer.parseInt` đặc biệt hữu ích khi cần kiểm tra độ dài, đầu vào rỗng, thông báo lỗi dễ hiểu, số nguyên ngoài phạm vi hoặc yêu cầu nhập lại. Ngoài ra, với số thực có dấu chấm thập phân cố định, có thể đọc cả dòng rồi gọi `Double.parseDouble(line.strip())`; cách này parse theo cú pháp của `Double`, **khác** quy tắc locale của `Scanner.nextDouble()`.

## 7. `nextDouble()` cũng có vấn đề tương tự

Vấn đề không chỉ xảy ra với `nextInt()`. Các phương thức đọc token như `nextLong()`, `nextFloat()`, `nextDouble()` cũng không tự hoàn tất dòng.

Tạo **`DoubleRemainderDemo.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class DoubleRemainderDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("8.5\nGood progress\n")) {
            scanner.useLocale(Locale.US);

            double score = scanner.nextDouble();
            scanner.nextLine(); // consume remainder of score line
            String note = scanner.nextLine();

            System.out.printf(Locale.US, "score=%.1f%n", score);
            System.out.println("note=" + note);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out DoubleRemainderDemo.java
java -cp out DoubleRemainderDemo
```

**Stdout chính xác:**

```text
score=8.5
note=Good progress
```

`Locale.US` khiến scanner hiểu token `8.5` theo quy tắc dấu chấm thập phân, đồng thời `printf(Locale.US, ...)` in dấu chấm trong kết quả. Nếu chương trình dùng `nextDouble()` theo locale mặc định, việc parse `8.5` có thể không đúng như mong đợi trên máy dùng quy ước dấu thập phân khác.

## 8. Những trường hợp cần xét trước khi bỏ phần dư

| Dữ liệu đầu vào | Sau khi gọi `nextInt()` | Cách xử lý phù hợp |
| --- | --- | --- |
| `21\nAn\n` | `nextLine()` đầu tiên trả `""` | Có thể bỏ phần dư rồi đọc dòng tên |
| `21   \nAn\n` | Phần dư của dòng có ba dấu cách | Có thể bỏ phần dư rồi đọc dòng tên |
| `21 An\n` | Phần dư là `" An"` | Giữ `nextLine()` và lấy tên từ phần dư |
| `21 3\n` | Còn token `3` trên cùng dòng | Tiếp tục đọc token theo cấu trúc input, đừng bỏ dòng tùy tiện |
| `21\n\nAn\n` | Sau khi bỏ dòng tuổi, dòng tiếp theo thật sự rỗng | Quyết định có cho phép dòng rỗng không; không tự skip hết các dòng rỗng |
| Chỉ có `21` rồi EOF | Không có dòng tên | Kiểm tra `hasNextLine()`, báo input thiếu thay vì gọi vô điều kiện |
| Nhập chữ `abc` khi đang gọi `nextInt()` | Số chưa được đọc thành công; `InputMismatchException` có thể xảy ra | Xử lý lỗi token, không áp dụng bước bỏ phần dư như thể đã đọc số hợp lệ |

Cần lưu ý `nextLine()` không luôn trả về rỗng; chính xác hơn, nó trả **phần còn lại của dòng hiện tại**, loại bỏ dấu kết thúc dòng. Nếu sau token là khoảng trắng, văn bản hoặc tab, chúng có thể nằm trong phần dư.

## 9. Xuống dòng trên Windows, Linux và macOS

Các dòng văn bản có thể kết thúc bởi ký tự LF (`\n`) hoặc cặp CRLF (`\r\n`). `Scanner.nextLine()` nhận diện ranh giới dòng theo quy tắc của Scanner và trả nội dung dòng **không kèm dấu kết thúc dòng**.

Vì thế trong trường hợp thông thường, bạn không phải kiểm tra chuỗi có chứa `\r` cuối dòng để sửa lỗi `nextInt()` rồi `nextLine()`; nguyên nhân chính vẫn là ranh giới **token và dòng**.

Nếu dùng `System.out.printf(...)`, có thể kết thúc dòng bằng `%n` để phù hợp nền tảng; ký hiệu này dành cho **đầu ra**, không thay đổi cách `Scanner` đọc input.

Mã nguồn đặt trong string literal như `"21\nAn\n"` chứa các ký tự escape được Java giải mã thành LF lúc chương trình chạy. Khi nhập từ terminal thực, cách terminal echo và gửi ký tự xuống dòng có thể khác, nhưng quy tắc mức cao của `nextLine()` vẫn như trên.

## 10. Khi nào không nên gọi `nextLine()` “bỏ newline”?

Không nên viết thành thói quen cố định rằng sau **mọi** lời gọi `nextInt()` phải gọi thêm `nextLine()`. Điều đó sẽ làm mất dữ liệu nếu một dòng chứa nhiều token.

Ví dụ input:

```text
3 8 12
```

Nếu mục tiêu là đọc ba số, cách đúng là:

```java
int a = scanner.nextInt();
int b = scanner.nextInt();
int c = scanner.nextInt();
```

Không có lý do thêm `scanner.nextLine();` sau số đầu tiên, vì làm thế sẽ bỏ `8 12`. Đoạn trên cần một `Scanner` đã khởi tạo; nó minh họa chiến lược đọc token, không phải chương trình độc lập.

Tương tự, nếu nhập `21 Nguyen Van An` trên một dòng, `scanner.nextLine()` sau `nextInt()` chính là cơ hội lấy **họ tên còn lại**. Phải **lưu kết quả** thay vì bỏ đi.

Để thiết kế chương trình rõ ràng, hãy quyết định trước:

1. **Mỗi giá trị trên một dòng**: chọn `nextLine()` cho toàn bộ các trường, sau đó parse số; dễ xác thực và báo lỗi.
2. **Nhiều token số trong một dòng**: tiếp tục đọc bằng `nextInt()`/`nextDouble()` hoặc `next()` theo thứ tự.
3. **Token đầu là số, phần còn lại là văn bản cùng dòng**: đọc số bằng `nextInt()`, rồi **giữ phần dư** qua `nextLine()`.
4. **Số ở dòng riêng, văn bản ở dòng kế tiếp**: sau `nextInt()` có thể gọi `nextLine()` một lần để bỏ phần dư, rồi mới đọc dòng kế; cần kiểm tra EOF.

## 11. Lỗi thường gặp và phương án khắc phục

**Lỗi 1 — cho rằng `nextInt()` tiêu thụ luôn Enter.** Thực tế nó phân tích token số, không tự chuyển sang dòng sau. Sửa bằng cách chọn chiến lược đọc nhất quán hoặc xử lý phần dư.

**Lỗi 2 — dùng `nextLine()` rồi tiếp tục chờ tên mà không kiểm tra kết quả.** Hãy in kết quả vào dấu ngoặc vuông lúc debug (`"[" + name + "]"`) để thấy tên rỗng hoặc chỉ chứa khoảng trắng.

**Lỗi 3 — gọi bỏ dòng trước khi chắc chắn đọc số thành công.** Nếu `nextInt()` gặp token sai, nó có thể ném `InputMismatchException`, nên luồng xử lý thông thường sẽ không đến bước kế tiếp. Dùng `hasNextInt()` hoặc `try/catch` phù hợp.

**Lỗi 4 — vô tình làm mất dữ liệu cùng dòng.** `scanner.nextLine();` sẽ bỏ toàn bộ phần còn lại của dòng, không chỉ “xóa một ký tự newline”. Trước khi bỏ, phải biết định dạng input bảo đảm phần dư không có dữ liệu cần dùng.

**Lỗi 5 — giả định lúc nào cũng còn dòng tiếp theo.** Với nguồn đọc từ file, pipe hoặc EOF, có thể không còn dòng. Dùng `hasNextLine()` khi cần và xử lý thiếu dữ liệu.

**Lỗi 6 — dùng nhiều Scanner trên cùng `System.in`.** Các scanner có bộ đệm riêng, có thể cạnh tranh dữ liệu khi cùng đọc một luồng. Nên dùng một scanner chung, truyền vào những phương thức cần đọc và quản lý vòng đời phù hợp.

**Lỗi 7 — nhầm với sai locale.** `nextDouble()` không parse được `8.5` có thể do thiết lập `Locale`, không phải newline. Kiểm tra lỗi định dạng số trước, rồi mới xử lý ranh giới dòng.

**Lỗi 8 — đóng `Scanner(System.in)` quá sớm.** Đóng scanner thường đóng luôn luồng `System.in` bên dưới. Trong chương trình đơn giản kết thúc sau nhập liệu, `try-with-resources` như ví dụ là phù hợp; trong ứng dụng lớn, cần một nơi sở hữu vòng đời luồng console.

## 12. Bài tập tự kiểm tra

**Câu 1.** Với input `10\nHello\n`, sau `scanner.nextInt();`, lần `scanner.nextLine()` kế tiếp trả gì?

**Đáp án:** Chuỗi rỗng `""`; dòng `Hello` chưa được đọc.

**Câu 2.** Với input `10 World\n`, có nên bỏ kết quả của `nextLine()` sau khi đọc số nếu cần `World` không?

**Đáp án:** Không. Phần dư `" World"` chứa dữ liệu cần dùng; lưu lại và loại dấu cách đầu nếu quy tắc input cho phép.

**Câu 3.** `scanner.nextInt(); scanner.nextLine(); scanner.nextLine();` có luôn hợp lệ không?

**Đáp án:** Không. Phải biết cấu trúc input, còn đủ dòng và các lời gọi trước đã thành công hay chưa. Cách gọi này còn có thể bỏ nhầm dữ liệu trên dòng số.

**Câu 4.** Có thể tránh trộn hai phương thức bằng cách nào?

**Đáp án:** Đọc từng trường qua `nextLine()`, sau đó `Integer.parseInt` hoặc `Double.parseDouble` và xử lý ngoại lệ/giới hạn tương ứng.

**Câu 5.** Vì sao `nextLine()` đầu tiên sau một số không nhất thiết rỗng?

**Đáp án:** Vì nó lấy toàn bộ **phần dư của dòng**, có thể gồm khoảng trắng hoặc văn bản sau token số.

**Ghi nhớ:** Phần xuống dòng “còn lại” sau `nextInt()`/`nextDouble()` là hệ quả của việc đọc **token**, trong khi `nextLine()` đọc **phần còn lại của dòng**. Cách sửa đúng phụ thuộc dữ liệu nằm ở dòng tiếp theo hay cùng dòng với số. Đọc theo dòng rồi parse thường là lựa chọn rõ ràng nhất cho form console.
