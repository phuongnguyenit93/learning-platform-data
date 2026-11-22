# Locale, dấu phân cách thập phân và trách nhiệm đóng nguồn nhập trong Java

## 1. Vì sao nhập số có thể khác nhau giữa các máy?

Khi người dùng nhập một số thực, cách viết dấu phân cách thập phân và dấu phân nhóm hàng nghìn tùy thuộc **quy ước vùng miền** (*locale*). Ví dụ:

| Locale | Số một nghìn hai trăm ba mươi tư phẩy năm | Ý nghĩa |
| --- | --- | --- |
| `Locale.US` | `1,234.50` | Dấu phẩy nhóm hàng nghìn, dấu chấm thập phân |
| `Locale.GERMANY` | `1.234,50` | Dấu chấm nhóm hàng nghìn, dấu phẩy thập phân |

Cả hai cách viết biểu diễn **cùng giá trị số**, nhưng văn bản đầu vào khác nhau. Nếu dùng `java.util.Scanner` để đọc một số, trình phân tích token của `Scanner` có thể chịu ảnh hưởng của locale. Nếu dùng `System.out.printf` hoặc `String.format` để hiển thị số, ký tự thập phân và phân nhóm cũng có thể thay đổi theo locale.

**Hai việc cần tách bạch:**

1. **Đọc/parsing:** chuyển văn bản như `"1.234,50"` thành giá trị `double`.
2. **Hiển thị/formatting:** chuyển giá trị `1234.5` thành văn bản theo quy ước cần dùng.

Không nên coi dấu phẩy và dấu chấm là những ký tự có ý nghĩa giống nhau trong mọi locale. Đồng thời không nên mặc định thiết lập locale trên máy học của mình sẽ giống hệ thống chấm bài hay máy người dùng.

## 2. `Scanner` đọc số theo locale

`Scanner` là lớp trong package `java.util`. Nó đọc đầu vào theo token và có các phương thức như `nextInt()`, `nextDouble()`, `next()` và `nextLine()`.

```java
import java.util.Locale;
import java.util.Scanner;

// Mã trong phương thức:
try (Scanner scanner = new Scanner("12.75")) {
    scanner.useLocale(Locale.US);
    double value = scanner.nextDouble(); // 12.75
}
```

- `scanner.useLocale(Locale.US)` đặt locale dùng khi `Scanner` phân tích số.
- `nextDouble()` lấy token kế tiếp và phân tích thành giá trị `double` theo locale đã chọn.
- `nextInt()` cũng dùng các quy tắc số nguyên liên quan đến locale và radix hiện tại.
- `next()` chỉ đọc một token dạng `String`, không tự chuyển thành số.
- `nextLine()` đọc phần còn lại của dòng thành `String`, không tự phân tích nội dung dòng thành số.

Nếu không gọi `useLocale`, `Scanner` dùng locale mặc định phù hợp của môi trường khi khởi tạo. Không nên viết test phụ thuộc vào điều đó. Trong ví dụ có kết quả dự kiến chính xác, hãy **chỉ rõ locale**.

### Cùng giá trị, hai cách nhập

```java
try (Scanner us = new Scanner("1,234.50");
     Scanner de = new Scanner("1.234,50")) {
    us.useLocale(Locale.US);
    de.useLocale(Locale.GERMANY);

    double a = us.nextDouble(); // 1234.5
    double b = de.nextDouble(); // 1234.5
}
```

Các chuỗi được dùng ở đây có định dạng nhóm nghìn/thập phân đúng theo hai locale đã chọn. Kết quả trong biến `a` và `b` là **giá trị số**, không còn mang theo cách viết dấu phẩy hay dấu chấm ở nguồn ban đầu.

Nếu token không hợp lệ theo locale hoặc nằm ngoài các dạng mà `Scanner` chấp nhận, `nextDouble()` có thể ném `InputMismatchException`. Nếu nguồn đã hết, có thể gặp `NoSuchElementException`; nếu `Scanner` đã đóng, thao tác đọc có thể ném `IllegalStateException`.

## 3. Kiểm tra với `hasNextDouble()` và xử lý dữ liệu sai

`hasNextDouble()` kiểm tra token kế tiếp có thể được `Scanner` phân tích thành `double` theo các quy tắc hiện tại hay không. Nó **không tiêu thụ** token.

```java
import java.util.Locale;
import java.util.Scanner;

// Đặt trong phương thức:
try (Scanner scanner = new Scanner("abc 12.5")) {
    scanner.useLocale(Locale.US);

    if (!scanner.hasNextDouble() && scanner.hasNext()) {
        String invalid = scanner.next(); // Tiêu thụ "abc"
        System.out.println("Invalid: " + invalid);
    }

    if (scanner.hasNextDouble()) {
        double number = scanner.nextDouble(); // 12.5
        System.out.println("Number: " + number);
    }
}
```

Điểm quan trọng: nếu `hasNextDouble()` trả `false` mà vòng lặp cứ kiểm tra cùng token, chương trình có thể lặp mãi. Cần **loại bỏ token không hợp lệ**, yêu cầu nhập lại hoặc dừng theo chính sách lỗi đã chọn.

`hasNextDouble()` kiểm tra **cú pháp đọc được thành số thực**, không kiểm tra điều kiện nghiệp vụ như “giá trị phải lớn hơn 0” hoặc “phải là số hữu hạn”. Nếu dữ liệu số cần hữu hạn, kiểm tra thêm `Double.isFinite(value)`. Không phải mọi giá trị kiểu `double` đều phù hợp với miền dữ liệu ứng dụng.

Đừng dùng `catch (Exception e) { }` rỗng để che dữ liệu nhập sai. Với chương trình console, thông báo lỗi rõ ràng và vòng lặp nhập lại thường có ích hơn.

## 4. `Double.parseDouble()` không phân tích theo locale

`Double.parseDouble(String)` xử lý các biểu diễn số thực theo cú pháp được Java quy định, **không dùng locale mặc định của người dùng** để diễn giải dấu phân cách thập phân. Ví dụ:

```java
double a = Double.parseDouble("12.5"); // 12.5

// Double.parseDouble("12,5");
// Ném NumberFormatException: dấu phẩy không được hiểu là dấu thập phân.
```

Nếu muốn đọc số thực từ một **dòng văn bản cố định** với cú pháp dấu chấm thập phân, có thể dùng `Scanner.nextLine()`, sau đó `Double.parseDouble(text.trim())`. Cách này tránh vấn đề trộn `nextDouble()` với `nextLine()` và giúp cú pháp nhập rõ ràng.

Ngược lại, nếu muốn chấp nhận văn bản theo định dạng địa phương như `"1.234,50"`, dùng `Scanner` với `Locale.GERMANY` hoặc một parser phù hợp như `NumberFormat` với locale và quy tắc kiểm tra dữ liệu mong muốn. Không nên thay mọi dấu phẩy bằng dấu chấm một cách máy móc: trong một số locale, dấu phẩy là dấu thập phân, trong locale khác lại là dấu nhóm nghìn. Việc thay thế không đúng có thể làm **đổi giá trị** của số.

| API | Có áp dụng locale khi đọc số không? | Ví dụ |
| --- | --- | --- |
| `Scanner.useLocale(...)` + `nextDouble()` | Có | `"1.234,50"` với `Locale.GERMANY` |
| `Scanner.useLocale(...)` + `nextInt()` | Có, theo quy tắc số nguyên/radix | `"123"` với `Locale.US` |
| `Double.parseDouble("12.5")` | Không | Nhận dấu chấm theo cú pháp Java |
| `Integer.parseInt("123")` | Không | Nhận cú pháp số nguyên Java, không phải parser nhóm nghìn theo locale |
| `Scanner.nextLine()` | Không tự phân tích số | Đọc dòng văn bản, sau đó tự chọn quy tắc parse |

## 5. Locale cũng ảnh hưởng đến `printf()`

Khi in số thực, `System.out.printf` có overload nhận `Locale`:

```java
double price = 1234.5;

System.out.printf(Locale.US, "US: %,.2f%n", price);
System.out.printf(Locale.GERMANY, "DE: %,.2f%n", price);
```

Đoạn này cần `import java.util.Locale;` và đặt trong phương thức. Stdout tương ứng:

```text
US: 1,234.50
DE: 1.234,50
```

Trong `%,.2f`:

- `%f` định dạng số thực ở dạng thập phân.
- `.2` chọn hai chữ số sau dấu phân cách thập phân.
- Dấu `,` ngay trong **mẫu định dạng** bật tính năng nhóm chữ số; dấu nhóm thực tế trong kết quả phụ thuộc locale.
- `%n` tạo ký tự kết thúc dòng theo nền tảng.

Nếu bỏ đối số `Locale`, cách hiển thị có thể thay đổi theo locale mặc định của môi trường. `String.format(Locale.US, ...)` cũng tạo một chuỗi định dạng theo quy tắc tương ứng nhưng **không tự in** ra console.

**Phân biệt hai loại dấu phẩy:** dấu `,` trong chuỗi format `"%,.2f"` là ký hiệu **bật grouping**, không phải cam kết luôn in dấu phẩy ra kết quả. Với `Locale.GERMANY`, dấu grouping hiển thị là dấu chấm, còn dấu thập phân là dấu phẩy.

## 6. `Scanner.close()` đóng cái gì?

`Scanner` triển khai `java.io.Closeable` và cung cấp phương thức `close()`. Khi đóng, nó đánh dấu scanner đã đóng; nếu nguồn đầu vào bên dưới triển khai `Closeable`, scanner **cũng gọi `close()` trên nguồn đó**.

Vì thế, phải hỏi một câu quan trọng: **mã này có sở hữu nguồn nhập hay không?**

### Nguồn do chương trình tự mở: nên đóng

Ví dụ dùng `Scanner` để đọc một tệp do chính phương thức mở:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

class FileReaderExample {
    static void showFirstToken(Path file) throws IOException {
        try (Scanner scanner =
                new Scanner(file, StandardCharsets.UTF_8)) {
            if (scanner.hasNext()) {
                System.out.println(scanner.next());
            }
        } // Scanner được tự đóng tại đây.
    }
}
```

Đây là **lớp minh họa** không có `main`. Với constructor `Scanner(Path, Charset)` trên Java 17, ta có thể chỉ rõ charset cho tệp. `try-with-resources` tự gọi `close()` khi rời khối, kể cả khi có `return` hoặc ngoại lệ phát sinh trong thân khối.

Đóng đúng lúc đặc biệt quan trọng với những nguồn như file hoặc stream do chương trình sở hữu. Không nên trông chờ Garbage Collector tự giải phóng mọi tài nguyên bên ngoài.

### `Scanner(String)`: phù hợp cho ví dụ/test, có thể đóng tại cuối phạm vi

```java
try (Scanner scanner = new Scanner("Java 17")) {
    System.out.println(scanner.next());
}
```

Nguồn này là một chuỗi đã có trong bộ nhớ; ví dụ không mở một tệp hay đóng `System.in`. Đóng scanner vẫn đúng với nguyên tắc không dùng lại một đối tượng đọc sau khi kết thúc phạm vi.

### `Scanner(System.in)`: chú ý nguồn chung

`System.in` là **luồng nhập chuẩn dùng chung của tiến trình Java**. Khi viết:

```java
Scanner console = new Scanner(System.in);
```

scanner sử dụng `System.in` làm nguồn. Nếu gọi `console.close()`, `Scanner` cũng có thể đóng `System.in` bên dưới. Điều đó ảnh hưởng những phần khác của chương trình muốn tiếp tục đọc từ `System.in`. **Không nên đóng tùy tiện một scanner bọc `System.in` khi nguồn nhập còn được các thành phần khác dùng.**

Trong ứng dụng console đơn giản, có thể tạo **một scanner dùng chung** và giữ nó tới khi toàn bộ quá trình nhập kết thúc, thay vì tạo và đóng nhiều scanner trên `System.in`. Ở ranh giới kết thúc ứng dụng, chiến lược đóng tài nguyên phụ thuộc **ai được giao quyền sở hữu** luồng. Nếu phương thức chỉ **mượn** scanner do nơi khác cung cấp, phương thức ấy thường không nên tự đóng nó.

Không nên hiểu sai rằng `Scanner` không bao giờ phải đóng: quy tắc chính là **người sở hữu nguồn quyết định vòng đời**, chứ không phải “luôn đóng” hoặc “không bao giờ đóng” mọi scanner.

## 7. Chương trình Java 17+ chạy độc lập, không phụ thuộc locale máy

Tạo tệp **`LocaleInputDemo.java`**:

```java
import java.io.StringReader;
import java.util.Locale;
import java.util.Scanner;

public class LocaleInputDemo {
    static double read(String text, Locale locale) {
        try (Scanner scanner = new Scanner(text)) {
            scanner.useLocale(locale);
            if (!scanner.hasNextDouble()) {
                throw new IllegalArgumentException("invalid number");
            }
            double result = scanner.nextDouble();
            if (!Double.isFinite(result)) {
                throw new IllegalArgumentException("non-finite number");
            }
            return result;
        }
    }

    static class TrackedReader extends StringReader {
        boolean closed;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            super.close();
            closed = true;
        }
    }

    public static void main(String[] args) {
        double us = read("1,234.50", Locale.US);
        double de = read("1.234,50", Locale.GERMANY);

        System.out.printf(Locale.US, "US input: %.2f%n", us);
        System.out.printf(Locale.US, "DE input: %.2f%n", de);

        System.out.printf(Locale.US, "US output: %,.2f%n", us);
        System.out.printf(Locale.GERMANY, "DE output: %,.2f%n", de);

        double plain = Double.parseDouble("12.5");
        System.out.println("parseDouble: " + plain);

        try {
            Double.parseDouble("12,5");
        } catch (NumberFormatException ex) {
            System.out.println("parseDouble rejects comma");
        }

        try (Scanner scanner = new Scanner("abc 7.5")) {
            scanner.useLocale(Locale.US);
            if (!scanner.hasNextDouble() && scanner.hasNext()) {
                System.out.println("bad token: " + scanner.next());
            }
            System.out.printf(Locale.US, "next: %.1f%n",
                    scanner.nextDouble());
        }

        TrackedReader source = new TrackedReader("hello");
        try (Scanner scanner = new Scanner(source)) {
            System.out.println("owned input: " + scanner.next());
        }
        System.out.println("source closed: " + source.closed);
    }
}
```

Chạy tại thư mục có tệp với **JDK 17 trở lên**. Các lệnh hoạt động trên PowerShell/CMD (Windows) và bash/zsh (Linux/macOS):

```bash
javac -encoding UTF-8 LocaleInputDemo.java
java LocaleInputDemo
```

**Stdout chính xác** (lệnh biên dịch thành công không in gì):

```text
US input: 1234.50
DE input: 1234.50
US output: 1,234.50
DE output: 1.234,50
parseDouble: 12.5
parseDouble rejects comma
bad token: abc
next: 7.5
owned input: hello
source closed: true
```

### Giải thích ví dụ

1. Hai hàm `read` sử dụng `Scanner.useLocale` riêng cho từng chuỗi, nên `"1,234.50"` và `"1.234,50"` cùng được đọc thành giá trị `1234.5`.
2. Khi định dạng bằng `Locale.US`, giá trị hiển thị là `1,234.50`; khi dùng `Locale.GERMANY`, là `1.234,50`. Giá trị số **không thay đổi**, chỉ cách hiển thị khác.
3. `Double.parseDouble("12.5")` hợp lệ, còn `Double.parseDouble("12,5")` ném `NumberFormatException`, vì API đó không tự dùng dấu phẩy theo locale.
4. `hasNextDouble()` phát hiện token đầu `abc` không hợp lệ, `next()` loại bỏ nó rồi `nextDouble()` đọc `7.5`.
5. `TrackedReader` là một `StringReader` tự định nghĩa để theo dõi trạng thái đóng nguồn. Khi rời `try (Scanner ...)`, scanner đóng nguồn `source` và cờ `closed` thành `true`.

Bằng cách dùng các chuỗi đầu vào và chỉ định `Locale`, chương trình **không cần người dùng nhập tay** và không phụ thuộc locale mặc định của máy đang chạy.

## 8. Mẫu đọc bàn phím: quyết định nơi đóng `Scanner`

Ví dụ nhập một dòng số thực bằng dấu chấm thập phân, đồng thời có thông báo lỗi:

```java
import java.util.Scanner;

public class KeyboardNumber {
    public static void main(String[] args) {
        Scanner input = new Scanner(System.in);
        System.out.print("Enter number with a dot: ");

        if (input.hasNextLine()) {
            String text = input.nextLine().trim();
            try {
                double value = Double.parseDouble(text);
                if (!Double.isFinite(value)) {
                    System.err.println("Number must be finite.");
                } else {
                    System.out.println("Value: " + value);
                }
            } catch (NumberFormatException ex) {
                System.err.println("Invalid number.");
            }
        } else {
            System.err.println("No input.");
        }

        // Không đóng input ở đây: ví dụ xem System.in là nguồn dùng chung.
    }
}
```

Tệp tên **`KeyboardNumber.java`**, chạy:

```bash
javac -encoding UTF-8 KeyboardNumber.java
java KeyboardNumber
```

Đây là **chương trình có tương tác**: người dùng nhập dữ liệu rồi nhấn Enter; kết quả phụ thuộc chuỗi được nhập. Ví dụ nếu nhập `12.5`, stdout sau prompt chứa `Value: 12.5`. Vì `Double.parseDouble()` dùng cú pháp độc lập locale, ví dụ **chủ động quy định** nhập dấu chấm. Nếu yêu cầu của ứng dụng là nhập số theo locale người dùng, thay đổi cơ chế parse cho phù hợp thay vì ghi lời hướng dẫn mâu thuẫn.

Lưu ý về trình kiểm tra resource leak: với mã mượn `System.in`, một số công cụ phân tích tĩnh có thể nhắc scanner chưa được đóng. Không nên giải quyết bằng cách **đóng luôn nguồn chuẩn dùng chung** nếu yêu cầu chương trình là tiếp tục dùng nguồn đó ở nơi khác; thay vào đó, xác định ranh giới sở hữu và vòng đời rõ ràng.

## 9. Những lỗi thường gặp

| Lỗi hoặc giả định | Giải thích/cách sửa |
| --- | --- |
| `Scanner.nextDouble()` đọc sai ở máy có locale khác | Chỉ định `useLocale(Locale.US)` hoặc locale phù hợp định dạng dữ liệu |
| Nghĩ `Double.parseDouble("1,5")` đọc được số thực theo locale dùng dấu phẩy | Không; `parseDouble` không dùng locale; dùng parser phù hợp hoặc thay đổi cú pháp đầu vào có kiểm soát |
| Chỉ đổi dấu phẩy thành dấu chấm trên mọi chuỗi số | Có thể thay đổi ý nghĩa dấu nhóm/thập phân, nhất là với giá trị như `1,234` |
| Quên locale khi viết `printf("%.2f", value)` trong bài có stdout cần chính xác | Chỉ định `printf(Locale.US, ...)` khi cần kết quả theo dấu chấm |
| Tưởng `hasNextDouble()` đã đọc mất token | Chưa; nó chỉ kiểm tra, phải gọi `nextDouble()` hoặc tiêu thụ token theo logic |
| Bắt ngoại lệ rồi tiếp tục thử lại trên cùng token sai mà không loại bỏ | Vòng lặp có thể gặp lại lỗi; dùng `next()` hoặc đọc lại dòng với quy tắc cụ thể |
| Luôn đóng mọi `Scanner(System.in)` ngay sau một phương thức | Có thể đóng luôn `System.in` mà phần khác còn cần |
| Không bao giờ đóng `Scanner` đọc từ file | Làm tài nguyên file có thể còn mở; dùng `try-with-resources` với nguồn mình sở hữu |
| Tạo nhiều scanner độc lập trên cùng `System.in` | Dễ dẫn đến khó kiểm soát buffer và vòng đời; dùng một scanner có phạm vi dùng chung hợp lý |
| Nhầm đóng scanner với việc dọn bộ nhớ của GC | `close()` xử lý vòng đời tài nguyên, không chỉ việc thu gom đối tượng Java |

## 10. Checklist trước khi xây dựng luồng nhập

1. **Định dạng dữ liệu đến từ đâu?** Nếu là giao thức/file quy định dấu chấm thì parser phải theo cú pháp đó; nếu là nhập liệu người dùng theo locale, chọn parser theo locale.
2. **Đọc token hay đọc dòng?** Khi dùng `nextDouble()` rồi `nextLine()`, nhớ xử lý ký tự kết thúc dòng còn lại. Nếu dữ liệu phân tách theo dòng, cân nhắc dùng `nextLine()` nhất quán rồi parse.
3. **Cần số hợp lệ tới mức nào?** Sau khi parse, kiểm tra phạm vi, điều kiện dương/không âm, `Double.isFinite` theo miền nghiệp vụ.
4. **Ai sở hữu nguồn?** Tệp/stream tự mở thì đóng đúng lúc, ưu tiên `try-with-resources`; nguồn chuẩn `System.in` dùng chung thì không tự đóng giữa chừng.
5. **Output có cần tái lập giống nhau?** Dùng `printf(Locale.US, ...)` hoặc locale được chỉ định thay vì phụ thuộc thiết lập máy.

**Ghi nhớ:** `Locale` quyết định cách nhiều API như `Scanner.nextDouble()` nhận diện dấu phân cách thập phân và cách `printf()` trình bày số. `Double.parseDouble()` lại dùng cú pháp không phụ thuộc locale. Với `Scanner.close()`, hãy quản lý theo **quyền sở hữu nguồn nhập**: đóng các nguồn mình tạo và không vô tình đóng `System.in` khi chương trình còn cần nó.