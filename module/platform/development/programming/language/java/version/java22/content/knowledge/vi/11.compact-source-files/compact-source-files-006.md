# Đọc đầu vào, xuất kết quả và xử lý lỗi cho chương trình dòng lệnh nhỏ

Từ Java 25, các chương trình console nhỏ có thể dùng `java.lang.IO` để đọc từng dòng từ standard input và ghi kết quả ra standard output. Kết hợp với compact source file và instance main method, ta có thể viết một tiện ích dòng lệnh mà không cần khai báo class tường minh hoặc viết `public static void main(String[] args)`.

`IO` là API stable từ JDK 25 theo JEP 512. JDK 27 tiếp tục hỗ trợ API này; không cần preview flag. Bài tập trung vào cách đọc dữ liệu, kiểm tra đầu vào, xuất thông báo và xử lý ba tình huống thường gặp: người dùng nhập sai định dạng, kết thúc luồng đầu vào (EOF) và lỗi I/O.

## 1. API console đơn giản với java.lang.IO

`java.lang.IO` là class chứa các phương thức static để làm việc với `System.in` và `System.out` theo từng dòng.

| Phương thức | Tác dụng |
|---|---|
| `IO.print(value)` | Ghi nội dung ra standard output, không tự xuống dòng |
| `IO.println(value)` | Ghi nội dung rồi xuống dòng |
| `IO.println()` | Chỉ ghi ký tự xuống dòng |
| `IO.readln()` | Đọc một dòng từ standard input |
| `IO.readln(prompt)` | Ghi lời nhắc rồi đọc một dòng |

Ví dụ:

```java
void main() {
    IO.print("Hello");
    IO.println(", Java!");
    IO.println("This is a new line.");
}
```

Kết quả:

```text
Hello, Java!
This is a new line.
```

`print` hữu ích khi cần hiển thị nhiều phần trên cùng một dòng. `println` phù hợp với thông báo hoặc kết quả cần kết thúc dòng.

Trong compact source file, tên class `IO` có sẵn vì nó thuộc `java.lang`. Tuy nhiên, các phương thức static của class không được tự động static import. Vì vậy, hãy gọi `IO.println(...)` hoặc `IO.readln(...)`, không viết trần `println(...)`.

## 2. Đọc một dòng và xử lý trường hợp EOF

`IO.readln()` trả về một `String` không chứa ký tự kết thúc dòng. Nếu đã đến cuối luồng đầu vào mà không đọc được ký tự nào, phương thức trả về `null`.

Overload `IO.readln(prompt)` hiển thị lời nhắc rồi đọc dữ liệu:

```java
void main() {
    String name = IO.readln("Your name: ");

    if (name == null) {
        IO.println();
        IO.println("Input ended. Goodbye.");
        return;
    }

    IO.println("Hello, " + name + "!");
}
```

Khi chạy, chương trình hiển thị lời nhắc và chờ người dùng nhập một dòng. Nếu người dùng gửi EOF (ví dụ `Ctrl+D` trên Unix-like terminal hoặc `Ctrl+Z` rồi Enter trên Windows console), `readln` có thể trả về `null`.

EOF là trạng thái kết thúc đầu vào bình thường, không phải chuỗi rỗng và cũng không phải lỗi định dạng. Cần kiểm tra `null` trước khi gọi `trim()`, `strip()` hoặc các phương thức xử lý chuỗi khác.

Chuỗi rỗng (`""`) là trường hợp người dùng gửi một dòng không có ký tự. Nó khác với EOF. Tùy nghiệp vụ, chương trình có thể yêu cầu nhập lại khi chuỗi rỗng.

## 3. Nhập số: phân tích và xác thực dữ liệu

`readln` luôn trả về chuỗi. Nếu cần một số nguyên, hãy phân tích chuỗi bằng `Integer.parseInt` hoặc `Integer.valueOf`.

Các chuỗi như `""` (rỗng), `abc` hoặc `12.5` không phải biểu diễn hợp lệ của số nguyên và sẽ gây `NumberFormatException`.

Ví dụ chỉ phân tích một lần:

```java
void main() {
    String line = IO.readln("Enter quantity: ");

    if (line == null) {
        IO.println("No input was received.");
        return;
    }

    try {
        int quantity = Integer.parseInt(line.strip());
        IO.println("Quantity: " + quantity);
    } catch (NumberFormatException error) {
        IO.println("Please enter a whole number.");
    }
}
```

Đối với chương trình tương tác, thường nên yêu cầu người dùng nhập lại thay vì kết thúc ngay khi có lỗi định dạng. Có thể đóng gói vòng lặp này trong một method trợ giúp:

```java
Integer readPositiveInt(String prompt) {
    while (true) {
        String line = IO.readln(prompt);

        if (line == null) {
            return null;
        }

        try {
            int value = Integer.parseInt(line.strip());

            if (value > 0) {
                return value;
            }
        } catch (NumberFormatException ignored) {
            // Chuỗi không biểu diễn được một số nguyên.
        }

        IO.println("Enter a positive whole number and try again.");
    }
}
```

Method trả về:

- Một số nguyên dương nếu người dùng nhập hợp lệ.
- `null` nếu đầu vào kết thúc trước khi nhận được giá trị hợp lệ.

`NumberFormatException` chỉ được bắt quanh thao tác phân tích số. Không nên bắt mọi `RuntimeException` hoặc mọi `Exception` để che khuất lỗi lập trình không liên quan đến dữ liệu nhập.

## 4. Ví dụ hoàn chỉnh: tính tổng tiền cho một mặt hàng

Chương trình sau hỏi tên mặt hàng, số lượng và đơn giá. Chương trình kiểm tra dữ liệu, yêu cầu nhập lại nếu số không hợp lệ, xử lý EOF và phát hiện tràn số khi nhân số lượng với đơn giá.

```java
import java.io.IOError;

String readRequiredText(String prompt) {
    while (true) {
        String line = IO.readln(prompt);

        if (line == null) {
            return null;
        }

        String value = line.strip();

        if (!value.isEmpty()) {
            return value;
        }

        IO.println("This field cannot be empty.");
    }
}

Integer readPositiveInt(String prompt) {
    while (true) {
        String line = IO.readln(prompt);

        if (line == null) {
            return null;
        }

        try {
            int value = Integer.parseInt(line.strip());

            if (value > 0) {
                return value;
            }
        } catch (NumberFormatException ignored) {
            // Yêu cầu người dùng nhập lại.
        }

        IO.println("Enter a positive whole number.");
    }
}

void main() {
    try {
        String productName = readRequiredText("Product name: ");

        if (productName == null) {
            IO.println();
            IO.println("Input ended. No order was created.");
            return;
        }

        Integer quantity = readPositiveInt("Quantity: ");

        if (quantity == null) {
            IO.println();
            IO.println("Input ended. No order was created.");
            return;
        }

        Integer unitPrice = readPositiveInt("Unit price: ");

        if (unitPrice == null) {
            IO.println();
            IO.println("Input ended. No order was created.");
            return;
        }

        int total;
        try {
            total = Math.multiplyExact(quantity, unitPrice);
        } catch (ArithmeticException error) {
            IO.println("The total is too large to represent as an int.");
            return;
        }

        IO.println();
        IO.println("Order summary");
        IO.println("Product: " + productName);
        IO.println("Quantity: " + quantity);
        IO.println("Unit price: " + unitPrice);
        IO.println("Total: " + total);

    } catch (IOError error) {
        IO.println("Could not read from standard input: " + error.getMessage());
    }
}
```

Các điểm cần chú ý:

1. `readRequiredText` loại bỏ khoảng trắng ở đầu và cuối, sau đó yêu cầu giá trị không rỗng.
2. `readPositiveInt` chỉ trả về khi phân tích được số nguyên dương.
3. Các method trả về `null` để báo cho `main` biết luồng nhập đã kết thúc.
4. `NumberFormatException` được xử lý tại nơi phân tích số để người dùng có thể thử lại.
5. `Math.multiplyExact` phát hiện tràn số nguyên và ném `ArithmeticException` thay vì trả về một tổng sai do overflow.
6. `IOError` được bắt ở cấp `main` để xử lý lỗi đọc standard input.

Ví dụ dùng kiểu `int` để giữ phần tính toán đơn giản. Với tiền tệ thực tế, nên dùng `BigDecimal` và quy tắc làm tròn phù hợp với nghiệp vụ thay vì dùng số thực nhị phân hoặc giả định mọi giá trị tiền đều vừa với `int`.

## 5. Phân biệt lỗi nhập liệu, EOF và lỗi I/O

Ba tình huống này cần được xử lý riêng vì ý nghĩa của chúng khác nhau:

| Tình huống | Dấu hiệu | Cách xử lý thường dùng |
|---|---|---|
| Người dùng nhập sai định dạng | `NumberFormatException` khi parse | Hiển thị hướng dẫn và yêu cầu nhập lại |
| Người dùng kết thúc input | `readln` trả `null` | Dừng nhập, kết thúc chương trình hoặc hủy thao tác hiện tại |
| Có lỗi khi đọc dữ liệu | `IOError` | Hiển thị lỗi phù hợp và kết thúc thao tác đọc |

`IOError` là một `Error`, không phải checked exception. Tuy vậy, có thể bắt đúng loại lỗi này tại ranh giới I/O để chương trình console hiển thị thông báo dễ hiểu. Tránh bắt `Error` quá rộng vì có thể che khuất các lỗi nghiêm trọng của JVM hoặc lỗi lập trình.

Không nên dùng chuỗi đặc biệt như `-1` để biểu diễn EOF nếu `-1` cũng có thể là dữ liệu hợp lệ. Dùng `null` từ `readln` hoặc một kiểu kết quả rõ ràng giúp tránh nhầm lẫn.

## 6. Không trộn nhiều cách đọc trên System.in

Sau lần gọi `IO.readln` đầu tiên, `IO` khởi tạo bộ giải mã charset và có thể đọc đệm thêm byte từ `System.in`. Vì vậy, tài liệu API quy định việc tiếp tục dùng `System.in` bằng một cách đọc khác sau đó có hành vi không xác định.

Trong cùng một chương trình, không nên trộn:

- `IO.readln()` với `Scanner(System.in)`.
- `IO.readln()` với `BufferedReader` bọc `System.in`.
- `IO.readln()` với việc tự đọc byte từ `System.in`.

Hãy chọn một cơ chế đọc cho toàn bộ standard input. Nếu chương trình cần parsing phức tạp, định dạng đặc biệt hoặc đọc byte, hãy thiết kế toàn bộ luồng nhập bằng API phù hợp ngay từ đầu thay vì chuyển qua lại giữa nhiều reader.

`IO.readln` đọc theo dòng và bỏ ký tự kết thúc dòng. Charset được chọn theo thuộc tính `stdin.encoding`; nếu thuộc tính không tồn tại hoặc không nạp được charset được chỉ định, UTF-8 được dùng làm mặc định. Các chuỗi byte không hợp lệ được thay bằng ký tự thay thế của charset.

## 7. Khi nào nên dùng IO và khi nào cần API khác?

`java.lang.IO` phù hợp với chương trình console nhỏ cần đọc và ghi văn bản theo dòng. Nó không phải API tổng quát cho mọi loại I/O.

| Nhu cầu | API phù hợp |
|---|---|
| Đọc một dòng từ console | `IO.readln()` |
| Hiển thị lời nhắc và đọc một dòng | `IO.readln(prompt)` |
| In thông báo console | `IO.print/println` |
| Đọc và ghi tệp văn bản | `Files` cùng charset tường minh, hoặc reader/writer phù hợp |
| Đọc dữ liệu nhị phân | `InputStream`, `ByteBuffer` hoặc API I/O chuyên biệt |
| Giao tiếp mạng | `java.net.http` hoặc API socket phù hợp |
| Nhập mật khẩu không hiển thị ký tự | `System.console().readPassword()` khi môi trường cung cấp console |

Nếu cần nhập mật khẩu, không nên dùng `IO.readln` vì ký tự người dùng nhập được gửi qua luồng console thông thường. `System.console()` có thể trả về `null` trong IDE, service hoặc môi trường không có console tương tác; cần xử lý trường hợp đó trước khi gọi `readPassword`.

`System.out.println` và `System.in` vẫn là API hợp lệ cho các trường hợp cần kiểm soát thấp hơn. `IO` là tiện ích cho console line-oriented, không phải lý do để thay thế mọi API I/O khác.

## 8. Phiên bản và ranh giới stable/preview trên JDK hiện đại

Tại ngày 25/11/2026:

- JDK 27 là feature release mới nhất, GA ngày 15/09/2026.
- JDK 25 là LTS mới nhất.
- Compact Source Files và Instance Main Methods (JEP 512) là tính năng final từ Java 25. `java.lang.IO` là class stable trong `java.lang` từ Java 25.
- Scoped Values (JEP 506) cũng final từ Java 25. `ScopedValue` hữu ích khi cần truyền dữ liệu ngữ cảnh bất biến qua các lời gọi phương thức trong một phạm vi thực thi; chương trình console đọc từng dòng không cần dùng nó.
- Structured Concurrency vẫn là preview API trên JDK 27 theo JEP 533 (Seventh Preview). Không coi `StructuredTaskScope` là API stable và không cần đưa nó vào một chương trình console tuần tự.

Nếu một ứng dụng khác thực sự thử `StructuredTaskScope` trên JDK 27, phải bật preview cả khi biên dịch lẫn chạy:

```bash
javac --enable-preview --release 27 Example.java
java --enable-preview Example
```

Preview chỉ áp dụng cho JDK release tương ứng; class file phụ thuộc preview của một release không phải artifact tương thích để chạy trên JDK release khác. Các ví dụ `IO` trong bài này là stable từ Java 25 nên không dùng các cờ trên.

Lưu ý về lịch sử: `IO` từng xuất hiện dưới dạng preview trong package `java.io` ở Java 22–24. API stable từ Java 25 chuyển sang `java.lang.IO` và dùng `System.in/System.out`. Khi viết code mới, dùng API final của JDK 25 trở lên thay vì sao chép import hoặc giả định từ các ví dụ preview cũ.

## Kết luận

Với chương trình dòng lệnh nhỏ, `IO.readln` đọc dữ liệu theo dòng, `IO.print/println` xuất kết quả và `java.lang.IO` cung cấp một cách làm gọn, stable từ Java 25. Cần phân biệt chuỗi rỗng, EOF (`null`), lỗi định dạng (`NumberFormatException`) và lỗi I/O (`IOError`).

Hãy xác thực dữ liệu ngay tại nơi phân tích, chỉ bắt loại exception dự kiến, dừng có kiểm soát khi EOF và không trộn nhiều cơ chế đọc `System.in`. Cách tổ chức này giúp chương trình console ngắn gọn mà vẫn xử lý được những tình huống nhập liệu thường gặp trên JDK hiện đại.

## Tài liệu tham khảo

- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [JEP 506: Scoped Values](https://openjdk.org/jeps/506)
- [JEP 533: Structured Concurrency (Seventh Preview), JDK 27](https://openjdk.org/jeps/533)
- [Java SE 27 API — java.lang.IO](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/IO.html)
- [Java SE 27 API — java.io.IOError](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/IOError.html)
- [Java SE 27 API — java.lang.ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html)
- [Oracle Java 27 — Structured Concurrency](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html)
- [Oracle Java 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [JEP 12: Preview Features](https://openjdk.org/jeps/12)
