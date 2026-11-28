# Sử dụng IO để đọc đầu vào và in kết quả trong chương trình nhỏ

## Mục tiêu học tập

Trong **Java 25**, bạn có thể tạo một chương trình nguồn gọn (*compact source file*) chỉ với một phương thức `void main()`, sau đó đọc dữ liệu và in kết quả qua các phương thức tĩnh của **`java.lang.IO`**. Không cần khai báo `public class` chỉ để chạy một ví dụ ngắn, cũng không cần tạo `Scanner` chỉ để lấy một dòng văn bản.

Đây là nội dung của chương **Tệp nguồn gọn**, thuộc module **JAVA_VERSION_JAVA25**. Trong phạm vi học các khả năng Java 25 vẫn còn áp dụng cho phát triển Java hiện đại, bài này tập trung vào **IO dòng lệnh**, cách xử lý dữ liệu nhập hợp lệ, kết thúc luồng (EOF), chạy bằng terminal/pipe và thời điểm nên chuyển sang API I/O chuyên dụng.

Sau bài học, người học có thể:

1. Giải thích vai trò của `java.lang.IO` và mối liên hệ với compact source file trong Java 25.
2. Dùng đúng **năm phương thức** `IO.print(Object)`, `IO.println(Object)`, `IO.println()`, `IO.readln()` và `IO.readln(String)`.
3. Phân biệt dòng rỗng với EOF; không xử lý `null` như một chuỗi hợp lệ.
4. Chuyển đầu vào dạng `String` sang số, kiểm tra lỗi cú pháp và xử lý trường hợp tràn số.
5. Chạy chương trình tương tác hoặc chuyển dữ liệu từ stdin bằng pipe và chuyển hướng file.
6. Chọn cách in thông báo phù hợp với chương trình cho người dùng và chương trình chạy tự động.
7. Tránh nhầm API chính thức Java 25 với cú pháp từ những bản preview cũ.

> **Yêu cầu môi trường:** **JDK 25 trở lên** với JEP 512 đã chính thức hóa. Dùng `java -version` và `javac -version` để xác nhận phiên bản thực tế của công cụ. Các ví dụ trong bài không cần `--enable-preview`. Các kết quả in ra có thể khác về tiếng Việt/đường dẫn nếu terminal dùng bộ mã hoặc thiết lập hiển thị khác.

## 1. Vì sao Java 25 có `java.lang.IO`?

Trước đây, để giải thích một chương trình nhập tên và in lời chào, người học thường phải tiếp xúc sớm với `class`, `public static void main(String[] args)`, `System.in`, `System.out` và các lớp đọc luồng. Những API đó vẫn hợp lệ và quan trọng, nhưng làm dài một bài tập chỉ cần một dòng nhập.

**JEP 512 — Compact Source Files and Instance Main Methods** đã trở thành tính năng chính thức trong Java 25. Bên cạnh cú pháp tệp nguồn gọn, Java 25 có lớp **`java.lang.IO`** cung cấp các thao tác đơn giản trên **standard input** và **standard output**.

Ví dụ `Hello.java`:

~~~java
// Java 25 — Hello.java
void main() {
    IO.println("Xin chào Java 25!");
}
~~~

Chạy tại thư mục chứa tệp:

~~~bash
java -version
java Hello.java
~~~

Kết quả:

~~~text
Xin chào Java 25!
~~~

Ở đây:

- `void main()` là **instance main method** hợp lệ trong Java 25.
- Trình biên dịch tạo lớp được khai báo ngầm cho compact source file; Java vẫn tổ chức code trong lớp.
- `IO` ở package **`java.lang`** nên có thể tham chiếu theo tên đơn giản mà không cần `import java.lang.IO;`.
- Các **phương thức static của IO không được import tự động**; phải viết `IO.println(...)`, không chỉ `println(...)` trừ khi tự thêm explicit static import.

`IO` không chỉ dành riêng cho compact source file. Một ordinary Java class ở Java 25 cũng có thể dùng `IO.readln` hoặc `IO.println`. Sự kết hợp với compact syntax chỉ làm ví dụ dễ đọc hơn.

## 2. Năm phương thức của `java.lang.IO`

Theo **Java SE 25 API Specification**, lớp `java.lang.IO` có những phương thức tĩnh sau:

| Phương thức | Tác dụng | Đặc điểm cần nhớ |
|---|---|---|
| `IO.print(Object value)` | In biểu diễn chuỗi của một giá trị ra stdout | **Không** tự thêm dấu xuống dòng |
| `IO.println(Object value)` | In giá trị rồi xuống dòng | Tương đương `System.out.println(value)` theo đặc tả |
| `IO.println()` | Chỉ in ký tự kết thúc dòng | Hữu ích để tạo một dòng trống |
| `IO.readln()` | Đọc một dòng từ stdin | Trả về `String`, hoặc `null` khi EOF |
| `IO.readln(String prompt)` | In lời nhắc rồi đọc một dòng từ stdin | Tương đương in prompt bằng `print` rồi gọi `readln()` |

Ví dụ `Output.java`:

~~~java
void main() {
    IO.print("Kết quả: ");
    IO.println(42);
    IO.println();
    IO.println("Hoàn tất");
}
~~~

Kết quả:

~~~text
Kết quả: 42

Hoàn tất
~~~

Ở dòng đầu, `IO.print("Kết quả: ")` **không xuống dòng**; vì vậy `42` được in trên cùng một dòng. `IO.println()` không nhận đối số và tạo một dòng trống giữa hai phần kết quả.

### 2.1. In số, chuỗi, boolean và đối tượng

`print(Object)` và `println(Object)` có một tham số kiểu `Object`. Bạn có thể truyền chuỗi, giá trị boolean, số nguyên hoặc các đối tượng khác; các kiểu nguyên thủy được boxing khi cần.

~~~java
void main() {
    int count = 5;
    double price = 12.5;
    boolean available = true;

    IO.println("Số lượng: " + count);
    IO.println("Đơn giá: " + price);
    IO.println("Còn hàng: " + available);
    IO.println((Object) null);
}
~~~

Dòng cuối in chữ `null`, không gây `NullPointerException` chỉ vì truyền một tham chiếu `null` vào `println(Object)`. Tuy nhiên, khi **nhận `null` từ `readln()`**, bạn phải xử lý logic EOF trước khi gọi các phương thức như `trim()`, `strip()` hoặc `isBlank()` trên biến đó.

Muốn định dạng số hoặc văn bản, có thể dùng các API Java hiện hành như `String.format(...)` hoặc `"...".formatted(...)`, sau đó truyền chuỗi thành phẩm vào `IO.println`. **`IO` không có phương thức `printf`** trong Java 25; `System.out.printf` vẫn hợp lệ khi cần điều khiển định dạng trực tiếp.

### 2.2. `readln(prompt)` không tự xuống dòng ở prompt

Tệp `Ask.java`:

~~~java
void main() {
    String name = IO.readln("Bạn tên gì? ");
    IO.println("Dữ liệu nhận được: " + name);
}
~~~

Một phiên làm việc tương tác có thể hiển thị:

~~~text
Bạn tên gì? Lan
Dữ liệu nhận được: Lan
~~~

Phần `Lan` trên dòng đầu là **dữ liệu do người dùng nhập**, và việc terminal có hiển thị lại ký tự đang gõ hay không phụ thuộc môi trường terminal. `IO.readln("Bạn tên gì? ")` chỉ ghi prompt ra stdout rồi đọc; nó không tự nối thêm `\\n` vào prompt.

Có thể viết tương đương:

~~~java
void main() {
    IO.print("Bạn tên gì? ");
    String name = IO.readln();
    IO.println("Xin chào, " + name);
}
~~~

Cách dùng `IO.readln("...")` thường súc tích hơn trong chương trình hỏi đáp nhỏ. Đối với xử lý tự động bằng pipe, nên cân nhắc **không in prompt vào stdout**, vì stdout thường là dữ liệu đầu ra được chương trình khác tiêu thụ.

## 3. Chương trình nhập tên có xử lý EOF và dòng trống

Một lời gọi `IO.readln()` trả về:

- **Một `String` không chứa ký tự kết thúc dòng** khi đọc được một dòng.
- **Chuỗi rỗng `""`** khi người dùng chỉ nhấn Enter trên một dòng trống.
- **`null`** khi đã đến cuối luồng (EOF) mà không đọc được ký tự nào.

Đây là ba tình huống khác nhau. Nếu code viết `name.strip()` ngay sau `IO.readln()`, một luồng rỗng từ pipe hoặc tệp có thể gây `NullPointerException`.

Ví dụ `Greeting.java`:

~~~java
void main() {
    String input = IO.readln("Nhập tên: ");

    if (input == null) {
        IO.println("Không có đầu vào (EOF).");
        return;
    }

    String name = input.strip();

    if (name.isEmpty()) {
        IO.println("Tên không được để trống.");
        return;
    }

    IO.println("Xin chào, " + name + "!");
}
~~~

Diễn giải từng bước:

1. Lấy một dòng đầu vào qua `readln`.
2. Kiểm tra EOF **trước** khi gọi phương thức trên chuỗi.
3. Dùng `strip()` để bỏ khoảng trắng đầu/cuối theo định nghĩa Unicode của Java; không thay đổi chữ ở giữa.
4. Xử lý dòng rỗng sau khi loại khoảng trắng.
5. In kết quả thân thiện và kết thúc.

Các bước này là nền tảng cho những bài tập nhập dữ liệu nhỏ và vẫn hữu ích khi sau này chuyển logic sang lớp thông thường, web controller hoặc service. Phần kiểm tra chuỗi không phụ thuộc vào compact source file.

### 3.1. EOF được tạo như thế nào?

EOF không phải chuỗi người dùng gõ `"EOF"`. Nó là trạng thái của **luồng đầu vào**. Ví dụ trên Linux/macOS:

~~~bash
printf 'Lan\n' | java Greeting.java
printf '' | java Greeting.java
printf '\n' | java Greeting.java
~~~

Ý nghĩa lần lượt:

- Đầu vào gồm một dòng `Lan` → lời chào.
- Đầu vào không có byte nào → `readln` trả về `null`, in thông báo EOF.
- Đầu vào gồm một dòng trống → `readln` trả về `""`, báo tên trống.

Trên Windows PowerShell, có thể dùng pipe với một chuỗi:

~~~powershell
"Lan" | java Greeting.java
~~~

Trong terminal tương tác, cơ chế gửi EOF phụ thuộc hệ điều hành và terminal (thường Ctrl+D trên Unix-like hoặc Ctrl+Z rồi Enter trên Windows console). Hãy ưu tiên thử với pipe/tệp để tái hiện tình huống rõ ràng.

> **Lưu ý kiểm thử:** khi redirect input, prompt từ `IO.readln("Nhập tên: ")` vẫn có thể xuất hiện trên stdout. Bởi vậy kết quả stdout không nhất thiết chỉ có dòng lời chào. Nếu dùng công cụ đối chiếu output tự động, hãy thiết kế giao diện dòng lệnh dành riêng cho chế độ batch.

## 4. Đọc số nguyên an toàn từ một dòng

`IO.readln` **luôn trả về chuỗi**, không tự chuyển thành `int`, `double` hay `BigDecimal`. Hãy chuyển kiểu một cách tường minh và phân biệt:

- Không có dòng đầu vào (`null`).
- Dòng trống, chỉ có khoảng trắng.
- Dòng không phải số (`NumberFormatException`).
- Dòng là số quá lớn hoặc quá nhỏ cho kiểu đích.
- Các giá trị ngoài phạm vi nghiệp vụ dù đúng cú pháp.

Một ví dụ chưa an toàn:

~~~java
void main() {
    int age = Integer.parseInt(IO.readln("Tuổi: "));
    IO.println("Tuổi của bạn: " + age);
}
~~~

Đoạn này dễ gặp lỗi khi EOF, nhập `abc` hoặc một giá trị quá lớn. Có thể chấp nhận nó để minh họa nhanh, nhưng không nên dùng làm mẫu cho chương trình cần xử lý dữ liệu thực.

### 4.1. Viết phương thức nhập số có thể thử lại

Tệp `Sum.java`:

~~~java
Integer readInteger(String prompt) {
    while (true) {
        String line = IO.readln(prompt);

        if (line == null) {
            return null; // EOF: không thể tiếp tục yêu cầu nhập.
        }

        String text = line.strip();

        if (text.isEmpty()) {
            IO.println("Vui lòng nhập một số nguyên.");
            continue;
        }

        try {
            return Integer.valueOf(text);
        } catch (NumberFormatException exception) {
            IO.println("Giá trị không hợp lệ, hãy nhập lại.");
        }
    }
}

void main() {
    Integer first = readInteger("Số thứ nhất: ");
    if (first == null) {
        IO.println("Đã hết đầu vào, dừng chương trình.");
        return;
    }

    Integer second = readInteger("Số thứ hai: ");
    if (second == null) {
        IO.println("Đã hết đầu vào, dừng chương trình.");
        return;
    }

    try {
        int sum = Math.addExact(first, second);
        IO.println("Tổng: " + sum);
    } catch (ArithmeticException exception) {
        IO.println("Tổng vượt phạm vi số nguyên 32 bit.");
    }
}
~~~

Chạy tương tác:

~~~bash
java Sum.java
~~~

Ví dụ phiên làm việc:

~~~text
Số thứ nhất: abc
Giá trị không hợp lệ, hãy nhập lại.
Số thứ nhất: 12
Số thứ hai: 30
Tổng: 42
~~~

**Tại sao cần từng phần?**

- `while (true)` cho phép nhập lại khi dữ liệu không đúng định dạng.
- `null` được dùng riêng làm tín hiệu EOF; phương thức kết thúc thay vì lặp vô hạn.
- `Integer.valueOf(text)` kiểm tra cú pháp và phạm vi của số nguyên 32 bit; nó có thể ném `NumberFormatException`.
- `Math.addExact` phát hiện **tràn số khi cộng**, một lỗi khác với số đầu vào không đúng định dạng.
- `try/catch` chỉ bao phạm vi có thể gây lỗi chuyển đổi/cộng số; không nuốt mọi exception và tiếp tục vô điều kiện.

Ở chương trình lớn hơn, tách hàm chuyển đổi và validation thành logic có thể kiểm thử độc lập, rồi cho IO đảm nhiệm lớp tương tác với người dùng.

### 4.2. Đọc dữ liệu tiền tệ

Đừng dùng `double` làm nguồn giá trị chuẩn cho các phép tính tiền tệ cần độ chính xác thập phân. Java hiện đại có `BigDecimal` trong `java.math` (thuộc `java.base`):

~~~java
void main() {
    String input = IO.readln("Giá sản phẩm (ví dụ 12.50): ");

    if (input == null || input.isBlank()) {
        IO.println("Không có giá hợp lệ.");
        return;
    }

    try {
        BigDecimal price = new BigDecimal(input.strip());

        if (price.signum() < 0) {
            IO.println("Giá không được âm.");
            return;
        }

        IO.println("Giá đã nhập: " + price.toPlainString());
    } catch (NumberFormatException exception) {
        IO.println("Giá không đúng định dạng thập phân.");
    }
}
~~~

Vì compact source file tự import on demand các public type từ `java.base`, tên `BigDecimal` có thể dùng trực tiếp. Nếu chuyển sang ordinary source file, cần import rõ `java.math.BigDecimal` hoặc dùng fully qualified name.

Ở hệ thống thanh toán thực, phải xác định đơn vị tiền tệ, dấu phân cách, scale, rounding mode và validation nghiệp vụ; `new BigDecimal(text)` chỉ giải quyết bước phân tích chuỗi, không tự xây dựng quy tắc tính tiền.

## 5. Đọc nhiều dòng đến EOF

Với đầu vào theo dòng, `IO.readln()` phù hợp để đọc dữ liệu liên tục cho đến khi hết luồng. Tệp `CountLines.java`:

~~~java
void main() {
    long nonBlankLines = 0;

    String line;
    while ((line = IO.readln()) != null) {
        if (!line.isBlank()) {
            nonBlankLines++;
        }
    }

    IO.println("Số dòng không trống: " + nonBlankLines);
}
~~~

Chạy với dữ liệu từ pipe:

~~~bash
printf 'Java\n\nSpring\nJDK 25\n' | java CountLines.java
~~~

Kết quả:

~~~text
Số dòng không trống: 3
~~~

Tại sao mẫu này hữu ích?

- `readln()` không in prompt: stdout chỉ chứa kết quả.
- Dòng rỗng không bị nhầm với EOF; vòng lặp tiếp tục cho tới khi `readln()` trả `null`.
- Có thể tái sử dụng bằng cách cung cấp stdin từ terminal, file hoặc chương trình khác.

Chuyển hướng một tệp văn bản vào stdin, trên terminal hỗ trợ redirection:

~~~bash
java CountLines.java < input.txt
~~~

Bản thân `IO` không tự kiểm tra kích thước dữ liệu hoặc giới hạn thời gian chờ. Chương trình đọc toàn bộ stdin theo dòng sẽ đợi mãi nếu bên gửi không đóng luồng hoặc người dùng không gửi EOF. Với dịch vụ nhận dữ liệu không tin cậy, cần thiết kế giới hạn và timeout thích hợp thay vì chỉ dựa vào vòng lặp vô hạn.

### 5.1. Dòng kết thúc được xử lý ra sao?

`IO.readln()` trả về nội dung **không gồm ký tự kết thúc dòng**. Thường gặp các dạng LF (`\\n`), CR (`\\r`) hoặc CRLF (`\\r\\n`) ở đầu vào, nhưng API trả về `String` của dòng đã đọc mà không kèm các ký tự phân tách dòng đó.

Ví dụ khi đọc file chứa:

~~~text
A
B
~~~

Các lần đọc lần lượt cho `"A"`, `"B"`, rồi `null`. Đừng tự `substring` để bỏ dấu xuống dòng: làm vậy có thể cắt mất ký tự cuối của dữ liệu hợp lệ.

## 6. Tạo menu tương tác bằng `IO.readln` và `IO.println`

Một chương trình nhỏ có thể kết hợp output, input và `switch` để xây dựng menu. Ví dụ `Menu.java`:

~~~java
void showMenu() {
    IO.println();
    IO.println("=== CHƯƠNG TRÌNH NHỎ ===");
    IO.println("1. Hiển thị lời chào");
    IO.println("2. Hiển thị thời điểm hiện tại");
    IO.println("0. Thoát");
}

void main() {
    while (true) {
        showMenu();

        String choice = IO.readln("Chọn chức năng: ");

        if (choice == null) {
            IO.println("Kết thúc đầu vào (EOF).");
            return;
        }

        switch (choice.strip()) {
            case "1" -> IO.println("Xin chào từ Java 25!");
            case "2" -> IO.println(Instant.now());
            case "0" -> {
                IO.println("Tạm biệt!");
                return;
            }
            default -> IO.println("Lựa chọn không hợp lệ.");
        }
    }
}
~~~

`Instant` thuộc `java.time` trong `java.base`, vì thế compact source file có thể dùng mà không cần khai báo import thông thường. Câu lệnh `switch` với `->` là cú pháp Java đã chính thức từ trước, vẫn được hỗ trợ trong Java 25.

Điểm thực hành quan trọng là nhánh `choice == null`. Nếu chỉ so sánh `choice.equals("0")` mà không kiểm tra EOF, chương trình có thể ném `NullPointerException` khi người dùng đóng stdin.

Không cần dùng `System.exit(0)` để thoát khỏi menu đơn giản: `return` từ `main` đã kết thúc chương trình trong ví dụ này. Khi ứng dụng lớn có tài nguyên đang mở, việc thoát cần tuân theo lifecycle tương ứng.

## 7. Dùng `main(String[] args)` khi muốn hỗ trợ chế độ batch

Chương trình tương tác và chương trình chạy bằng pipe có yêu cầu đầu ra khác nhau:

- Với **người dùng trong terminal**, prompt như `"Nhập tên: "` giúp tương tác dễ hiểu.
- Với **một pipeline hoặc script**, prompt thường gây khó xử lý vì nó xen vào dữ liệu stdout.

Trong Java 25, compact source file có thể khai báo `void main(String[] args)` thay vì `void main()`.

Ví dụ `Normalize.java`:

~~~java
void main(String[] args) {
    boolean batch = args.length == 1 && args[0].equals("--batch");

    String line = batch
            ? IO.readln()
            : IO.readln("Nhập mã sản phẩm: ");

    if (line == null || line.isBlank()) {
        System.err.println("Thiếu dữ liệu đầu vào.");
        return;
    }

    String normalized = line.strip().toUpperCase(Locale.ROOT);
    IO.println(normalized);
}
~~~

Chạy tương tác:

~~~bash
java Normalize.java
~~~

Chạy batch trên Linux/macOS:

~~~bash
printf '  ab-21 \n' | java Normalize.java --batch
~~~

Kết quả trên stdout khi ở chế độ batch:

~~~text
AB-21
~~~

Ở đây `Locale.ROOT` tránh phụ thuộc locale của máy khi chuyển chữ hoa cho mã định danh. Với đầu ra tự động, sử dụng `System.err.println` cho lỗi để không trộn thông báo lỗi với kết quả stdout. `System.err` vẫn là API hiện hành, không bị thay thế bởi `IO`.

**Giới hạn ví dụ:** nếu tham số dòng lệnh không đúng, `batch` sẽ là false và chương trình chuyển sang tương tác. Trong công cụ thực tế, hãy kiểm tra rõ số lượng/giá trị arguments và in hướng dẫn sử dụng; không nên tự động chuyển chế độ nếu có tham số bất ngờ.

## 8. Charset, chuyển hướng luồng và những điều không nên trộn lẫn

### 8.1. Cách `IO.readln` giải mã đầu vào trong Java 25

Theo đặc tả **`java.lang.IO`**:

- `readln()` và `readln(String)` đọc byte từ **`System.in`** rồi giải mã thành ký tự.
- Charset được chọn từ system property **`stdin.encoding`**.
- Nếu property không có hoặc charset không thể tải được, cơ chế đọc dùng **UTF-8** làm fallback.
- Byte malformed hoặc unmappable có thể được thay bằng chuỗi replacement của charset, thay vì bảo toàn nguyên byte.
- Việc thiết lập decoder diễn ra ở **lần gọi `readln` đầu tiên**.

Điều này quan trọng khi truyền file tiếng Việt: tệp được pipe vào stdin phải có bộ mã phù hợp với cấu hình giải mã. Không nên giả định stdin và stdout luôn sử dụng cùng một charset chỉ vì đều đi qua `IO`; `IO.print`/`IO.println` hoạt động như các phương thức của `System.out`.

Nếu một chương trình cần kiểm soát encoding, byte-level parsing, xử lý binary, charset errors hoặc kích thước bộ đệm, nên chọn các API chuyên dụng như `InputStream`, `Reader`, `Files`, với charset và chính sách lỗi được khai báo rõ.

### 8.2. Không trộn `IO.readln` với những cách đọc khác từ `System.in`

Đây là ràng buộc **được ghi trong Java SE 25 API Specification**:

> `readln` có thể đọc đệm thêm byte từ `System.in`. Sau lần gọi `readln` đầu tiên, việc tiếp tục sử dụng `System.in` bằng cách khác có hành vi không được đặc tả.

Ví dụ **không nên làm**:

~~~java
void main() {
    String first = IO.readln();

    // KHÔNG NÊN: trộn hai reader trên cùng System.in.
    Scanner scanner = new Scanner(System.in);
    String second = scanner.nextLine();

    IO.println(first + " / " + second);
}
~~~

`Scanner` vẫn là API Java hợp lệ; vấn đề ở đây là **trộn hai cách tiêu thụ cùng một luồng sau khi IO đã thiết lập bộ đệm**. Để đọc nhiều dòng, chọn một chiến lược xuyên suốt:

- Chỉ dùng `IO.readln` cho chương trình ngắn.
- Hoặc dùng `Scanner`/`BufferedReader`/`InputStreamReader` chuyên dụng từ đầu đến cuối nếu cần nhiều tính năng hơn.

Không tạo một `Scanner` mới cho mỗi lần nhập với hy vọng có thể chia sẻ bộ đệm an toàn; điều đó cũng có thể gây vấn đề và làm quản lý tài nguyên rối hơn.

### 8.3. Không dùng `IO.readln` để nhập bí mật

`IO.readln` không cung cấp cơ chế **ẩn ký tự đang gõ** hoặc xóa bộ nhớ nhạy cảm. Trong terminal thường gặp, password nhập bằng `readln` có thể xuất hiện trên màn hình. Khi cần nhập mật khẩu tương tác, dùng cơ chế phù hợp như `Console.readPassword` nếu môi trường có console và được thiết kế cho trường hợp đó, hoặc sử dụng secret manager/authentication flow của ứng dụng.

Đừng ghi password, access token hay dữ liệu cá nhân vào kết quả `IO.println`, log hoặc đầu ra CI chỉ để debug ví dụ.

## 9. `IO` khác gì `System.out`, `Scanner` và `Console`?

Không nên dạy rằng các API cũ đã lỗi thời chỉ vì `IO` xuất hiện trong Java 25. Chúng giải quyết **những phạm vi khác nhau**.

| Công cụ | Phù hợp | Hạn chế cần hiểu |
|---|---|---|
| `java.lang.IO` | Nhập một dòng, in kết quả, CLI nhỏ, compact source file | Ít phương thức; không thay thế parsing phức tạp hoặc giao diện bảo mật |
| `System.out`/`System.err` | Output chuẩn/lỗi và formatted output | Input phải dùng API khác |
| `Scanner` | Tách token, parse nhiều kiểu, đọc dữ liệu có cấu trúc đơn giản | Cần hiểu delimiter, locale, lifetime và buffering |
| `BufferedReader` | Đọc dòng có kiểm soát, kết hợp với Reader/charset | Phải tự chọn nguồn và quản lý tài nguyên |
| `java.io.Console` | Terminal có console, đọc password theo cơ chế hỗ trợ | `System.console()` có thể là `null` khi chạy từ IDE, pipe hoặc CI |
| `Files` / NIO.2 | File, Path, charset, tài nguyên I/O | Cần thiết kế xử lý IOException và path rõ ràng |

Ví dụ chương trình chạy bằng **pipe** vẫn dùng được `IO.readln` vì nó đọc từ `System.in`, không cần một console tương tác. Đây là ưu điểm của IO cho các công cụ nhỏ trong shell. Trái lại, `Console` không phải lúc nào cũng có trong môi trường chạy tự động.

### 9.1. Khi nào nên chuyển khỏi compact source file?

Nếu chương trình cần nhiều file, package được đặt tên, lớp công khai, unit tests cho nhiều thành phần, cơ chế DI, network/file I/O phức tạp hoặc tích hợp vào thư viện, hãy refactor thành ordinary Java classes và thiết kế rõ trách nhiệm.

Logic nhập/xuất nên đứng ở rìa chương trình; phần tính toán nghiệp vụ có thể chuyển sang phương thức thuần hoặc lớp riêng. Chẳng hạn, phép tính giá sau giảm không nên trực tiếp gọi `IO.readln` bên trong hàm dùng để unit test. Tách input, validation, calculation và output giúp chuyển từ chương trình học tập sang ứng dụng hiện đại dễ dàng hơn.

## 10. Những hiểu nhầm từ các bản preview cũ

JEP 512 đã trở thành tính năng **chính thức trong Java 25**. Trong các tài liệu preview Java 23/24, lớp IO và quy tắc import của nó khác với bản chính thức.

| Hiểu nhầm | Quy tắc nên dùng khi viết Java 25 |
|---|---|
| Phải bật `--enable-preview` để dùng compact source file | **Không** cần; JEP 512 đã final ở Java 25 |
| Dùng `java.io.IO` | Dùng **`java.lang.IO`** |
| Có thể gọi `println("Hello")` tự động trong compact file | Phải gọi **`IO.println("Hello")`** hoặc thêm explicit static import |
| `IO.readln` chỉ dùng được khi `System.console()` khác null | API Java 25 dựa trên **`System.in`**, dùng được với pipe/redirect |
| `IO.print` cũng tự xuống dòng | **Không**; `IO.println` mới tự xuống dòng |
| `IO.readln` sẽ trả chuỗi rỗng khi file đã kết thúc | EOF trả **`null`**; dòng rỗng trả `""` |
| Dùng `IO` nghĩa là không cần xử lý ngoại lệ/validation | Vẫn phải xử lý dữ liệu sai, EOF; `readln` có thể ném `IOError` khi lỗi I/O |

Các lỗi thời gian biên dịch hoặc hành vi runtime có thể do đang chạy JDK khác với mong đợi. Đừng dùng cú pháp preview chỉ vì gặp trong một blog cũ; hãy kiểm tra **Java SE 25 API Specification** và JEP đã được hoàn thiện.

### 10.1. Các lỗi thường gặp

| Biểu hiện | Khả năng gây ra | Cách xử lý |
|---|---|---|
| `cannot find symbol: IO` | JDK/source level chưa hỗ trợ `java.lang.IO` | Kiểm tra `java -version`, `javac -version` và toolchain Java 25 |
| `cannot find symbol: println` | Gọi `println` không có `IO.` hay explicit import | Sửa thành `IO.println(...)` |
| `NullPointerException` khi gọi `strip()` | Không kiểm tra EOF từ `readln` | So sánh `line == null` trước |
| `NumberFormatException` | Nhập không phải số hoặc vượt phạm vi kiểu | Chuẩn hóa/validate chuỗi và thông báo nhập lại |
| Kết quả cộng nguyên bị âm bất ngờ | Tràn số `int` | Dùng `Math.addExact`, `long` hoặc kiểu thích hợp |
| Mất dòng khi dùng `Scanner` sau `IO.readln` | Trộn bộ đệm của hai reader | Dùng một cơ chế đọc xuyên suốt |
| Prompt lẫn vào dữ liệu đưa qua pipe | Dùng `readln(prompt)` trong chế độ batch | Dùng `readln()` và output contract rõ ràng |
| Đọc sai tiếng Việt từ tệp | Charset của stdin không khớp cấu hình | Kiểm tra encoding, `stdin.encoding` và nguồn dữ liệu |
| Chương trình đợi mãi dù đã gửi dữ liệu | Chưa có newline hoặc EOF; luồng vẫn mở | Xác minh bên gửi hoàn tất dòng và đóng stdin |
| Chạy ví dụ từ tài liệu cũ bị lỗi | Ví dụ dùng cú pháp preview trước Java 25 | Đối chiếu JEP 512 và API chính thức |

## 11. Ma trận kiểm thử chương trình nhỏ

Không cần framework lớn để kiểm thử các chương trình trong bài. Khi học, hãy thực hiện các trường hợp sau với process Java 25 và ghi lại **stdout**, **stderr**, **exit code** cùng input đã gửi.

| Mã | Chương trình | Dữ liệu | Kết quả mong đợi |
|---|---|---|---|
| T1 | `Hello.java` | Không cần stdin | In câu chào, kết thúc bình thường |
| T2 | `Output.java` | Không cần stdin | `print` cùng dòng với giá trị và `println()` tạo dòng trống |
| T3 | `Greeting.java` | `Lan` | In `Xin chào, Lan!` |
| T4 | `Greeting.java` | Chỉ một dòng rỗng | Báo tên trống, không báo EOF |
| T5 | `Greeting.java` | Stdin rỗng (EOF ngay) | Báo không có đầu vào, không NPE |
| T6 | `Sum.java` | `12`, `30` | In tổng 42 |
| T7 | `Sum.java` | `abc`, `12`, `30` | Báo nhập lại rồi in 42 |
| T8 | `Sum.java` | `2147483647`, `1` | Phát hiện tràn số khi cộng |
| T9 | `CountLines.java` | 3 dòng không rỗng xen một dòng trống | In số dòng không trống bằng 3 |
| T10 | `Menu.java` | Lựa chọn `0` | Thoát, không lặp vô hạn |
| T11 | `Menu.java` | EOF trước lựa chọn | In thông báo EOF rồi kết thúc |
| T12 | `Normalize.java --batch` | `  ab-21 ` | Chỉ in `AB-21` trên stdout, không có prompt |

### 11.1. Gợi ý kiểm thử end-to-end bằng shell

Trên Linux/macOS:

~~~bash
printf '12\n30\n' | java Sum.java
printf 'abc\n12\n30\n' | java Sum.java
printf '2147483647\n1\n' | java Sum.java
printf '  ab-21 \n' | java Normalize.java --batch
~~~

Chú ý prompt của `Sum.java` được in lên stdout khi dữ liệu đến từ pipe; đó là **hành vi đã chọn của chương trình tương tác**. Với công cụ batch, hãy giữ stdout có định dạng ổn định để script khác có thể đọc.

Nếu kiểm tra output tự động, so sánh sau khi normalize line endings khi cần, không giả định Windows và Unix luôn dùng ký tự xuống dòng giống nhau.

## 12. Bài tập vận dụng

### Bài 1 — Máy tính bốn phép toán

Tạo `Calculator.java` dạng compact source file:

- Đọc hai số qua `IO.readln`.
- Đọc toán tử `+`, `-`, `*` hoặc `/`.
- Xử lý EOF, chuỗi trống, số không hợp lệ và chia cho 0.
- In kết quả bằng `IO.println`.
- Nếu dùng `double`, nêu rõ các giới hạn độ chính xác. Nếu dùng `BigDecimal`, chọn chính sách chia và làm tròn rõ ràng.

**Tiêu chí đạt:** đầu vào sai không khiến chương trình kết thúc bằng stack trace không cần thiết; có thông báo cụ thể và xử lý các trường hợp biên.

### Bài 2 — Thống kê dữ liệu từ stdin

Viết `Stats.java` chỉ dùng `IO.readln()` để đọc các dòng `số nguyên` tới EOF, sau đó in:

- Số lượng dòng hợp lệ.
- Tổng các số đã nhập.
- Số dòng không hợp lệ bị bỏ qua.

Dùng `Long.parseLong` hoặc kiểu phù hợp cho dữ liệu, và xác định cách xử lý khi tổng có thể vượt phạm vi. Kiểm thử cả stdin rỗng.

**Tiêu chí đạt:** không nhầm EOF với chuỗi rỗng, không lặp vô hạn khi hết input và output có thể đưa cho chương trình khác đọc.

### Bài 3 — Refactor thành ứng dụng dễ kiểm thử

Chuyển `Sum.java` sang ordinary Java source file có package:

- Tạo hàm `parseInteger(String)` hoặc validation tách riêng phần I/O.
- Viết unit test cho parser và phép cộng (bao gồm overflow).
- Giữ `IO.readln`/`IO.println` ở lớp entry point nếu vẫn là CLI.
- Nêu lý do ordinary class/package phù hợp hơn khi code được tái sử dụng.

**Tiêu chí đạt:** ứng dụng vẫn nhận và in kết quả đúng, logic xử lý số không phụ thuộc trực tiếp vào stdin/stdout và có thể kiểm thử độc lập.

## 13. Checklist áp dụng Java 25 hiện đại

Trước khi hoàn tất một chương trình dùng `java.lang.IO`, hãy kiểm tra:

- [ ] JDK đúng phiên bản **25+**, không yêu cầu preview flag cho JEP 512.
- [ ] Tệp nguồn gọn có `void main()` hoặc `void main(String[] args)` hợp lệ.
- [ ] Lời gọi IO dùng `IO.` hoặc explicit static import; không sao chép cú pháp preview cũ.
- [ ] Chọn đúng `print` (không xuống dòng) và `println` (xuống dòng).
- [ ] Có xử lý **`null` khi EOF** và phân biệt với dòng trống.
- [ ] Input được kiểm tra trước khi dùng để tính toán hoặc truy cập tài nguyên.
- [ ] Chọn một cơ chế đọc stdin; không trộn `IO.readln` với `Scanner(System.in)` sau đó.
- [ ] Đã xem xét charset và đầu ra tiếng Việt khi đọc từ file hoặc pipe.
- [ ] Chế độ batch không in prompt xen vào dữ liệu stdout; lỗi có thể đi qua stderr.
- [ ] Không nhập mật khẩu bằng cơ chế echo thông thường hoặc in bí mật ra output.
- [ ] Khi chương trình lớn lên, phần tính toán được tách khỏi I/O và tổ chức thành class/package phù hợp.

## Tài liệu tham khảo chính thức

- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): thiết kế và trạng thái chính thức của compact source files, instance main và `java.lang.IO`.
- [Java SE 25 API Specification — `java.lang.IO`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html): **nguồn chuẩn** cho cả năm phương thức, EOF, `stdin.encoding` và giới hạn khi dùng `System.in`.
- [Java SE 25 Language Guide — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): ví dụ compact source và cách dùng IO.
- [Java SE 25 Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận tính năng final và những thay đổi so với preview trước Java 25.
- [Java SE 25 API Specification — `java.io.Console`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): lựa chọn phù hợp khi cần thao tác với terminal có console, bao gồm nhập password.
