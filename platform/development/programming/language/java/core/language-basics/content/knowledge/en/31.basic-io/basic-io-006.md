# Phân biệt `next()`, `nextInt()` và `nextLine()` trong Java

## 1. Ba phương thức của `Scanner` đọc dữ liệu khác nhau

Lớp `java.util.Scanner` giúp đọc và phân tích dữ liệu từ bàn phím (`System.in`), chuỗi hoặc nguồn dữ liệu khác. Ba phương thức phổ biến là:

- **`next()`**: đọc **một token** và trả về `String`.
- **`nextInt()`**: đọc **một token biểu diễn số nguyên hợp lệ** và trả về giá trị `int`.
- **`nextLine()`**: đọc **phần còn lại của dòng hiện tại** và trả về `String`, bỏ ký tự kết thúc dòng ra khỏi kết quả.

Hai phương thức `next()` và `nextInt()` làm việc theo **token**; `nextLine()` làm việc theo **ranh giới dòng**. Sự khác biệt này là nguyên nhân thường gặp của lỗi “`nextLine()` bị bỏ qua” khi dùng chung với `nextInt()`.

```java
import java.util.Scanner;

// Đặt trong một phương thức:
Scanner sc = new Scanner(System.in);
String word = sc.next();
int age = sc.nextInt();
String text = sc.nextLine();
```

Đoạn trên chỉ minh họa cú pháp và **không phải chương trình độc lập**. Kết quả phụ thuộc dữ liệu được nhập và vị trí hiện tại của `Scanner` trong luồng.

## 2. Bảng so sánh nhanh

| Đặc điểm | `next()` | `nextInt()` | `nextLine()` |
| --- | --- | --- | --- |
| Trả về | `String` | `int` | `String` |
| Đơn vị đọc | Token | Token số nguyên | Phần còn lại của dòng |
| Khoảng trắng mặc định | Bỏ qua dấu phân cách trước token; dừng ở dấu phân cách sau token | Tương tự `next()`, đồng thời phân tích token theo quy tắc số nguyên | Giữ khoảng trắng trong nội dung dòng, không đưa ký tự kết thúc dòng vào kết quả |
| Dữ liệu `"Java Core"` | Lần đầu trả `"Java"` | Ném lỗi vì token đầu không phải số nguyên | Trả `"Java Core"` khi bắt đầu từ đầu dòng |
| Đọc số `42` | Trả chuỗi `"42"` | Trả số `42` | Trả chuỗi `"42"` nếu dòng chỉ có `42` |
| Nếu token đầu sai định dạng số | Vẫn có thể đọc token đó thành chuỗi | Có thể ném `InputMismatchException` | Không phân tích số, chỉ đọc nội dung dòng |
| Sau khi đọc | Thường để vị trí tại ranh giới sau token | Thường để vị trí tại ranh giới sau token | Tiêu thụ cả ký tự kết thúc dòng nếu có |

Với thiết lập mặc định, `Scanner` xem một hoặc nhiều ký tự **khoảng trắng theo định nghĩa Java** là dấu phân cách token (*delimiter*): dấu cách, tab, xuống dòng và nhiều ký tự whitespace khác. Có thể cấu hình delimiter khác bằng `useDelimiter(...)`, nên đừng khẳng định `next()` luôn tách theo dấu cách trong mọi chương trình.

**Lưu ý về `nextLine()`:** phương thức bắt đầu từ **vị trí đọc hiện tại**, không nhất thiết là đầu dòng. Nếu trước đó đã dùng `next()` hay `nextInt()`, phần còn lại của dòng có thể chỉ là chuỗi rỗng hoặc các dấu cách chưa tiêu thụ.

## 3. `next()`: đọc một token dạng chuỗi

Khi nhập:

```text
Nguyen Van An
```

và gọi:

```java
String first = sc.next();   // "Nguyen"
String second = sc.next();  // "Van"
String third = sc.next();   // "An"
```

`next()` sẽ bỏ qua dấu phân cách trước mỗi token và lấy token tiếp theo. Nó không tự ghép ba từ thành một tên đầy đủ.

Một trường hợp đáng chú ý:

```java
// Nếu đầu vào bắt đầu bằng: "Java 17"
String text = sc.next(); // "Java"
```

Dù `17` là số, `next()` vẫn chỉ trả về một `String`. Muốn xử lý con số, có thể gọi `nextInt()` ở lượt tiếp theo nếu token phù hợp, hoặc chuyển đổi chuỗi đã nhận bằng phương thức như `Integer.parseInt` sau khi kiểm tra dữ liệu.

Vì đọc token chứ không đọc dòng, `next()` không phù hợp để nhập **họ tên, địa chỉ, câu mô tả chứa nhiều từ** nếu cần giữ nguyên nội dung cả dòng.

## 4. `nextInt()`: đọc và phân tích một token số nguyên

Giả sử người dùng nhập:

```text
18 25
```

```java
int a = sc.nextInt(); // 18
int b = sc.nextInt(); // 25
```

`nextInt()` đọc từng token và chuyển sang `int`. Cần phân biệt:

- `next()` với token `18` trả về chuỗi `"18"`.
- `nextInt()` với token `18` trả về giá trị nguyên `18`.
- Token `"abc"` không phải `int` hợp lệ, nên `nextInt()` có thể ném `InputMismatchException`.
- Token biểu diễn số nằm **ngoài phạm vi của `int`** cũng có thể gây `InputMismatchException`.
- Nếu không còn token nào, phương thức có thể ném `NoSuchElementException`; nếu `Scanner` đã đóng thì các thao tác đọc có thể ném `IllegalStateException`.

Theo mặc định, `nextInt()` dùng radix 10 và phân tích số theo **locale** của `Scanner`. Có thể chỉ định radix bằng `nextInt(radix)` hoặc `useRadix`; locale cũng có thể ảnh hưởng cách đọc một số định dạng số. Đối với đầu vào đơn giản `18` hoặc `-7`, hành vi thông dụng là đọc được những giá trị tương ứng.

Nếu đang kiểm tra nhập số từ người dùng, thường nên kiểm tra trước bằng `hasNextInt()`:

```java
if (sc.hasNextInt()) {
    int age = sc.nextInt();
    System.out.println("Tuoi: " + age);
} else if (sc.hasNext()) {
    String invalid = sc.next(); // Tiêu thụ token không hợp lệ
    System.out.println("Khong phai so nguyen: " + invalid);
}
```

Đoạn này minh họa bên trong một phương thức. `hasNextInt()` chỉ **kiểm tra** token kế tiếp, không tự tiêu thụ token đó. Nếu nhận `false` rồi lại gọi `nextInt()` mà không thay đổi dữ liệu hoặc xử lý lỗi, bạn sẽ không khắc phục được vấn đề.

## 5. `nextLine()`: lấy phần còn lại của dòng

Khi bắt đầu đọc tại đầu dòng:

```text
Nguyen Van An
```

```java
String fullName = sc.nextLine(); // "Nguyen Van An"
```

`nextLine()` giữ các dấu cách giữa các từ trong chuỗi; nó trả về nội dung dòng **không chứa ký tự kết thúc dòng**. Phương thức này phù hợp để nhập tên đầy đủ, câu văn hoặc địa chỉ cần giữ khoảng trắng.

Nếu vị trí hiện tại đã ở giữa dòng, nó chỉ đọc **phần còn lại**:

```text
Java Core
```

```java
String first = sc.next();    // "Java"
String rest = sc.nextLine(); // " Core" (có dấu cách đầu chuỗi)
```

Hành vi trên có ý nghĩa quan trọng: `nextLine()` không tự bỏ khoảng trắng ở đầu nội dung như `next()`. Gọi `trim()` nếu muốn xóa dấu cách ở hai đầu, nhưng **chỉ làm thế khi yêu cầu nhập liệu thật sự cho phép** vì có thể làm thay đổi nội dung mà người dùng muốn giữ.

Nếu tới hết đầu vào và không còn dòng nào để đọc, `nextLine()` có thể ném `NoSuchElementException`. Khi đọc từ file/chuỗi, có thể dùng `hasNextLine()` trước khi gọi `nextLine()` để xử lý trường hợp hết dữ liệu.

## 6. Trộn token với dòng: kiểm tra phần dư trước khi bỏ

Với đầu vào hai dòng `20\nNguyen Van An\n`, `nextInt()` tiêu thụ token `20` nhưng `nextLine()` kế tiếp trả `""` vì nó chỉ lấy phần còn lại của dòng số. Muốn đọc dòng tên tiếp theo, bạn có thể **đọc bỏ phần dư** bằng một lần `nextLine()` rồi mới đọc lần nữa.

Cách này chỉ đúng khi tên thực sự ở dòng riêng. Với `20 Nguyen Van An\n`, phần dư của dòng số là `" Nguyen Van An"` và cần được **giữ lại**. Nếu chương trình quy định mỗi trường một dòng, có thể đọc `nextLine()` nhất quán rồi chuyển số bằng `Integer.parseInt`, xử lý `NumberFormatException`.

Chương trình chạy độc lập tiếp theo kiểm tra cả trường hợp phần dư rỗng, phần dư chứa số và token sai; bài chuyên về **phần xuống dòng còn lại** hướng dẫn chi tiết hơn về EOF, nhiều trường trên một dòng và cách phòng mất dữ liệu.

## 7. Chương trình Java 17+ chạy độc lập để quan sát chính xác

Để đầu ra xác định trên mọi máy mà không cần nhập tay, ví dụ dùng `Scanner` đọc từ **chuỗi đầu vào cố định**. Đây là cùng các phương thức áp dụng khi nguồn dữ liệu là `System.in`.

Tạo tệp **`ScannerReadDemo.java`**:

```java
import java.util.Scanner;

public class ScannerReadDemo {
    static void tokensAndLines() {
        String input = "Lan Nguyen\n27\nJava Core\n";
        try (Scanner scanner = new Scanner(input)) {
            System.out.println("next1=[" + scanner.next() + "]");
            System.out.println("next2=[" + scanner.next() + "]");
            System.out.println("nextInt=" + scanner.nextInt());
            System.out.println("afterInt=[" + scanner.nextLine() + "]");
            System.out.println("fullLine=[" + scanner.nextLine() + "]");
        }
    }

    static void remainingSameLine() {
        try (Scanner scanner = new Scanner("42  7\nHello world\n")) {
            System.out.println("number=" + scanner.nextInt());
            System.out.println("rest=[" + scanner.nextLine() + "]");
            System.out.println("line=[" + scanner.nextLine() + "]");
        }
    }

    static void recoverInvalidToken() {
        try (Scanner scanner = new Scanner("abc 15\n")) {
            if (!scanner.hasNextInt() && scanner.hasNext()) {
                System.out.println("bad=[" + scanner.next() + "]");
            }
            System.out.println("valid=" + scanner.nextInt());
        }
    }

    static void parseWholeLine() {
        try (Scanner scanner = new Scanner("20\nNguyen Van An\n")) {
            int age = Integer.parseInt(scanner.nextLine().trim());
            String name = scanner.nextLine();
            System.out.println("age=" + age);
            System.out.println("name=[" + name + "]");
        }
    }

    public static void main(String[] args) {
        tokensAndLines();
        remainingSameLine();
        recoverInvalidToken();
        parseWholeLine();
    }
}
```

Mở terminal tại thư mục chứa file, với **JDK 17 trở lên**, chạy giống nhau trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 ScannerReadDemo.java
java ScannerReadDemo
```

Kết quả **stdout chính xác** (biên dịch thành công không in gì):

```text
next1=[Lan]
next2=[Nguyen]
nextInt=27
afterInt=[]
fullLine=[Java Core]
number=42
rest=[  7]
line=[Hello world]
bad=[abc]
valid=15
age=20
name=[Nguyen Van An]
```

Giải thích:

1. Hai lần `next()` đọc `Lan` và `Nguyen`. `nextInt()` bỏ qua dấu xuống dòng và đọc số `27`.
2. `afterInt=[]` chứng minh lần gọi `nextLine()` sau `nextInt()` gặp ngay dấu xuống dòng của dòng `27`, nên nhận chuỗi rỗng; lần tiếp theo mới đọc `Java Core`.
3. Trong `"42  7\n"`, sau khi `nextInt()` lấy `42`, `nextLine()` trả về **hai dấu cách rồi `7`**; phần dư **không phải lúc nào cũng rỗng**.
4. `hasNextInt()` gặp token `abc` nên trả `false`, nhưng không tiêu thụ token; `next()` loại bỏ token đó, rồi `nextInt()` đọc `15`.
5. `parseWholeLine()` cho thấy cách đọc tuổi và họ tên theo từng dòng, chuyển chuỗi tuổi thành số bằng `Integer.parseInt`.

Trong ví dụ này, mỗi `Scanner` được tạo từ `String` rồi đóng bằng **try-with-resources**, không ảnh hưởng tới `System.in`. Đó là lý do chương trình tự chạy được và không cần tương tác bàn phím.

## 8. Dùng `Scanner(System.in)` trong chương trình có nhập bàn phím

Một mẫu đơn giản khi người dùng nhập tuổi và họ tên ở **hai dòng riêng**:

```java
import java.util.Scanner;

public class KeyboardInput {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.print("Nhap tuoi: ");
        int age = sc.nextInt();
        sc.nextLine(); // Tiêu thụ phần dư trên dòng tuổi
        System.out.print("Nhap ho ten: ");
        String name = sc.nextLine();
        System.out.println("Tuoi=" + age);
        System.out.println("Ten=" + name);
    }
}
```

Lưu thành **`KeyboardInput.java`**, biên dịch và chạy:

```bash
javac -encoding UTF-8 KeyboardInput.java
java KeyboardInput
```

Ví dụ nhập:

```text
20
Nguyen Van An
```

Khi đó hai dòng kết quả cuối chương trình là:

```text
Tuoi=20
Ten=Nguyen Van An
```

Đây là ví dụ **tương tác** nên các prompt `Nhap tuoi:` và `Nhap ho ten:` có thể xuất hiện chung dòng với nội dung người dùng gõ; đừng coi bản ghi màn hình terminal (có cả echo bàn phím) là stdout thuần cố định.

Một lưu ý về đóng tài nguyên: `Scanner.close()` sẽ đóng cả nguồn đầu vào bên dưới nếu nguồn đó triển khai `Closeable`. Khi dùng `new Scanner(System.in)`, đóng scanner có thể đóng luôn luồng **`System.in`** dùng chung, khiến phần khác của chương trình không còn đọc được. Với chương trình console nhỏ chỉ đọc một lần rồi kết thúc, có thể cân nhắc quyền sở hữu nguồn; với ứng dụng lớn, **không tạo rồi đóng nhiều scanner riêng trên cùng `System.in`**. Trong ví dụ bàn phím trên, scanner được giữ cho toàn bộ thời gian cần đọc và không đóng thủ công giữa chừng.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân / cách xử lý |
| --- | --- |
| `nextLine()` nhận chuỗi rỗng sau `nextInt()` | Dấu kết thúc dòng còn lại; nếu hai trường ở hai dòng, gọi một lần `nextLine()` để tiêu thụ phần dư |
| `next()` chỉ nhận một từ của họ tên | Nó đọc token, không đọc cả dòng; dùng `nextLine()` nếu cần đủ nội dung |
| `nextInt()` ném `InputMismatchException` | Token hiện tại không phải số nguyên phù hợp hoặc ngoài phạm vi `int`; kiểm tra với `hasNextInt()` và có chiến lược loại bỏ token lỗi |
| Chương trình cứ gặp cùng một token lỗi | `hasNextInt()` không tiêu thụ token; cần `next()`, đọc lại dòng hoặc thiết kế luồng nhập |
| `nextLine()` bị mất dữ liệu trên dòng số | Lệnh tiêu thụ phần dư đã loại cả nội dung sau số; thiết kế rõ dữ liệu cùng dòng hay khác dòng |
| Đọc tới hết dữ liệu gây `NoSuchElementException` | Kiểm tra `hasNext()` / `hasNextLine()` thích hợp trước khi đọc |
| Đọc sau khi đóng `Scanner` gây `IllegalStateException` | Không dùng scanner đã đóng; quản lý vòng đời nguồn vào |
| Có hai `Scanner` dùng cùng `System.in` gây hành vi khó hiểu | Dùng một scanner ở phạm vi hợp lý; đừng tự đóng nguồn còn dùng chung |
| Đọc chuỗi số bằng `nextLine()` nhưng `parseInt` thất bại | Xử lý `NumberFormatException`, quy định rõ chuỗi trống/khoảng trắng/phạm vi số |
| Tưởng `nextInt()` luôn lấy cả dòng | Nó chỉ đọc token số nguyên, không tự tiêu thụ dấu xuống dòng sau token |

## 10. Checklist quyết định cách đọc

1. Muốn nhập **một từ hoặc mã không có dấu phân cách**? Chọn `next()`.
2. Muốn nhập **một số nguyên từ token kế tiếp**? Chọn `nextInt()`, có kiểm tra dữ liệu sai khi cần.
3. Muốn nhập **cả tên/câu/dòng**? Chọn `nextLine()`.
4. Vừa đọc bằng phương thức token rồi muốn đọc dòng khác? Xem **có phần dư sau token** hay không; xử lý ranh giới dòng một cách có chủ đích.
5. Cần dữ liệu theo **từng dòng cố định**? Thường nên dùng `nextLine()` nhất quán rồi chuyển đổi giá trị, để mỗi lần đọc tiêu thụ một dòng.
6. Đọc file/chuỗi có thể hết bất ngờ? Dùng `hasNext()`, `hasNextInt()` hoặc `hasNextLine()` theo đúng phương thức định gọi.

**Ghi nhớ:** `next()` trả **một token dạng chuỗi**; `nextInt()` trả **một token số nguyên**; `nextLine()` trả **phần còn lại của dòng**, không chỉ token. Khi trộn đọc token với đọc dòng, phải hiểu vị trí quét và xử lý dấu xuống dòng còn lại để tránh mất dữ liệu.