# Giới thiệu StringBuilder khi cần ghép chuỗi lặp lại — Java 17+

## 1. Khi nào việc nối String trong vòng lặp thành vấn đề?

`String` trong Java là **bất biến** (*immutable*): sau khi tạo, nội dung của một đối tượng `String` không thể thay đổi. Biểu thức `text + value` tạo **giá trị chuỗi mới**. Nếu một vòng lặp liên tục tích lũy dữ liệu theo cách này, chương trình có thể phải sao chép ngày càng nhiều nội dung trung gian:

~~~java
String result = "";
for (int i = 1; i <= 5; i++) {
    result += i; // Giá trị String mới được tạo và gán lại cho result
}
System.out.println(result); // 12345
~~~

Đoạn trên **đúng chức năng**, nhất là với dữ liệu nhỏ. Tuy nhiên, khi số vòng lặp và độ dài chuỗi tăng, kiểu ghép lặp lại bằng `+=` có thể tạo nhiều chuỗi trung gian, làm tăng cấp phát và chi phí sao chép. Đây là một lý do quan trọng để dùng **`StringBuilder`**.

`StringBuilder` (thuộc `java.lang`) là một **đối tượng lưu dãy ký tự có thể thay đổi** (*mutable sequence of characters*). Nó hỗ trợ thêm dữ liệu vào cùng bộ dựng chuỗi thông qua `append(...)`, thay vì dùng `String` bất biến để lưu kết quả tạm sau từng vòng lặp.

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 5; i++) {
    builder.append(i);
}
String result = builder.toString();
System.out.println(result); // 12345
~~~

**Quy tắc thực tế:** dùng `+` cho vài thành phần đơn giản vì dễ đọc; cân nhắc `StringBuilder` khi xây dựng nội dung qua nhiều lần lặp, nhiều nhánh hoặc một quá trình có kích thước thay đổi.

## 2. Quy trình sử dụng StringBuilder

Ba bước cơ bản:

1. **Tạo bộ dựng**: `new StringBuilder()` hoặc `new StringBuilder("prefix")`.
2. **Thêm nội dung**: gọi `append(...)` trong vòng lặp; mỗi lời gọi cập nhật nội dung của builder.
3. **Chốt kết quả**: gọi `toString()` để nhận một giá trị `String` dùng cho API, hiển thị hoặc trả về.

~~~java
StringBuilder builder = new StringBuilder("Order:");
builder.append(' ').append(7);
builder.append(", paid=").append(true);

String message = builder.toString();
System.out.println(message); // Order: 7, paid=true
~~~

Các `append(...)` có thể **gọi nối tiếp** vì `append` trả về chính builder đang sử dụng. Java cung cấp overload cho `char`, `int`, `long`, `double`, `boolean`, `String`, `Object`, mảng ký tự và nhiều kiểu khác.

Điều cần phân biệt:

~~~java
StringBuilder builder = new StringBuilder("A");
String text = builder.toString(); // "A"
builder.append("B");

System.out.println(builder); // AB
System.out.println(text);    // A
~~~

`text` là giá trị `String` **không đổi**. Việc sửa builder sau đó không làm chuỗi đã lấy ra bằng `toString()` đổi theo.

## 3. Ghép danh sách trong vòng lặp: xử lý dấu phân cách

Một tình huống phổ biến là tạo văn bản từ nhiều phần tử, giữa chúng có dấu phẩy:

~~~java
static String joinNames(String[] names) {
    StringBuilder builder = new StringBuilder();
    for (int i = 0; i < names.length; i++) {
        if (i > 0) {
            builder.append(", ");
        }
        builder.append(names[i]);
    }
    return builder.toString();
}
~~~

Nếu `names = {"Lan", "Minh", "An"}`, kết quả là `Lan, Minh, An`.

**Vì sao kiểm tra `i > 0`?** Dấu phân cách chỉ xuất hiện **trước phần tử thứ hai trở đi**, nên không có dấu phẩy ở đầu hoặc cuối. Dùng chỉ số cũng xử lý ổn định trường hợp có phần tử là chuỗi rỗng (nếu được chấp nhận).

| Input | Output |
|---|---|
| `{"Lan", "Minh", "An"}` | `Lan, Minh, An` |
| `{"Lan"}` | `Lan` |
| Mảng rỗng `{}` | Chuỗi rỗng `""` |
| `{"A", "", "B"}` | `A, , B` |

Nếu **chỉ** cần nối những phần tử sẵn có bằng dấu phân cách, Java còn có API chuyên dụng:

~~~java
String value = String.join(", ", "Lan", "Minh", "An");
System.out.println(value); // Lan, Minh, An
~~~

Không cần viết builder thủ công khi `String.join` hoặc `Collectors.joining` đáp ứng đủ yêu cầu. Builder hữu ích hơn khi phải thêm nội dung theo điều kiện, từng vòng lặp hoặc trộn nhiều kiểu dữ liệu.

## 4. StringBuilder mutable, String immutable: khác nhau ở đâu?

~~~java
String first = "A";
String second = first + "B";

System.out.println(first);  // A
System.out.println(second); // AB
~~~

Biểu thức `first + "B"` tạo kết quả là một `String` khác về giá trị; `first` vẫn giữ văn bản `A`.

~~~java
StringBuilder builder = new StringBuilder("A");
builder.append("B");

System.out.println(builder); // AB
~~~

Lời gọi `append` **thay đổi nội dung builder**. Nếu hai biến tham chiếu cùng một builder, thay đổi sẽ được thấy qua cả hai:

~~~java
StringBuilder a = new StringBuilder("Hi");
StringBuilder alias = a;
alias.append("!");

System.out.println(a); // Hi!
~~~

Mã này không tạo bản sao builder; `alias = a` chỉ sao chép **giá trị tham chiếu**.

`final` cũng không khiến nội dung builder bất biến:

~~~java
final StringBuilder b = new StringBuilder("A");
b.append("B"); // Hợp lệ
// b = new StringBuilder("C"); // Lỗi: không gán lại biến final
~~~

**Kết luận:** `StringBuilder` có thể sửa nội dung; `String` không thể sửa nội dung. Đừng truyền builder cho những đoạn mã có thể thay đổi nó nếu bạn muốn giữ nguyên dữ liệu.

## 5. Những method nên biết đầu tiên

| Method | Công dụng | Ví dụ |
|---|---|---|
| `append(value)` | Thêm văn bản/giá trị cuối builder | `b.append(42)` |
| `toString()` | Lấy kết quả dạng `String` | `String s = b.toString();` |
| `length()` | Số UTF-16 code unit đang chứa | `b.length()` |
| `charAt(index)` | Đọc một code unit tại chỉ số | `b.charAt(0)` |
| `setCharAt(index, ch)` | Thay code unit tại chỉ số | `b.setCharAt(0, 'J')` |
| `insert(index, value)` | Chèn trước vị trí `index` | `b.insert(0, "Hi ")` |
| `delete(start, end)` | Xóa đoạn `[start, end)` | `b.delete(0, 3)` |
| `setLength(newLength)` | Đổi độ dài logic; có thể cắt ngắn hoặc mở rộng | `b.setLength(0)` |
| `capacity()` | Sức chứa hiện tại tính theo UTF-16 code unit | `b.capacity()` |
| `ensureCapacity(n)` | Yêu cầu sức chứa tối thiểu | `b.ensureCapacity(100)` |

Ví dụ chỉnh sửa:

~~~java
StringBuilder b = new StringBuilder("Java");
b.append(" 17");
b.insert(5, "Core "); // Java Core 17
b.delete(5, 10);       // Java 17
b.setCharAt(0, 'j');   // java 17

System.out.println(b); // java 17
~~~

**Lưu ý về chỉ số:** `charAt`, `setCharAt`, `insert`, `delete` sử dụng chỉ số **UTF-16 code unit**, không phải “mỗi ký tự người nhìn thấy = 1 vị trí”. Nếu nội dung có emoji hoặc ký tự Unicode ngoài BMP, một code point có thể chiếm hai code unit. Chỉnh sửa ở giữa surrogate pair có thể khiến văn bản không còn đúng như ý định.

`StringBuilder` có thêm API khác như `replace`, `reverse`, `indexOf`, `substring`. Người mới học chỉ cần nắm vững `append`, `toString`, `length` và cách quản lý dấu phân cách trước khi mở rộng sang nhiều thao tác.

## 6. Length và capacity không giống nhau

- `length()`: **số UTF-16 code unit của nội dung đang có**.
- `capacity()`: **sức chứa hiện tại** của bộ đệm, thường lớn hơn hoặc bằng `length()`.

~~~java
StringBuilder b = new StringBuilder(32);
System.out.println(b.length());   // 0
System.out.println(b.capacity()); // 32

b.append("Hi");
System.out.println(b.length());   // 2
System.out.println(b.capacity()); // 32
~~~

`new StringBuilder(32)` **không tạo chuỗi dài 32 ký tự**; nó tạo builder rỗng với sức chứa ban đầu 32 UTF-16 code unit.

Nếu biết tương đối kích thước kết quả, chỉ định dung lượng ban đầu giúp tránh một số lần mở rộng bộ đệm:

~~~java
StringBuilder report = new StringBuilder(128);
~~~

Tuy nhiên, không đoán một kích thước rất lớn vô cớ; hãy dựa vào dữ liệu thực tế. Việc nội bộ cấp phát/copy khi vượt capacity là chi tiết triển khai và thường được quản lý tự động.

Khi gọi `setLength(0)`, nội dung logic được xóa, nhưng **không được coi đó là thao tác xóa an toàn dữ liệu bí mật khỏi mọi vùng nhớ**. `StringBuilder` không phải cơ chế lưu trữ bí mật chuyên dụng.

## 7. Lỗi ghép lặp lại bằng String: nhìn bằng ví dụ, không đoán benchmark

Xem hai cách tạo kết quả tương tự:

~~~java
static String withPlus(int count) {
    String text = "";
    for (int i = 1; i <= count; i++) {
        text += i;
    }
    return text;
}

static String withBuilder(int count) {
    StringBuilder b = new StringBuilder();
    for (int i = 1; i <= count; i++) {
        b.append(i);
    }
    return b.toString();
}
~~~

Với `count = 5`, cả hai trả `"12345"`.

Khác biệt là **cách xây dựng**:

- `withPlus`: biến `text` lần lượt nhận các `String` kết quả qua phép nối trong nhiều lượt; với chuỗi tích lũy dài, cách này có thể gây nhiều chi phí cấp phát/sao chép trung gian.
- `withBuilder`: đối tượng builder được tạo một lần; các lần `append` thay đổi nội dung trong bộ đệm đang dùng.

Không nên khẳng định “`StringBuilder` luôn nhanh hơn trong mọi biểu thức”: compiler/JVM Java 17 có tối ưu hóa cho những phép nối đơn giản. Cần **benchmark đúng cách** nếu hiệu năng là mối quan tâm thực sự; phần này chủ yếu hướng dẫn **lựa chọn cấu trúc code phù hợp**.

Trong trường hợp ghép lặp lại với số phần tử tăng theo `n`, tổng công việc sao chép có thể tăng đáng kể nếu mỗi vòng phải xử lý cả phần nội dung đã ghép. Builder giúp giảm kiểu tăng trưởng chi phí đó bằng bộ đệm mutable.

## 8. Khi nào không cần StringBuilder?

**Một biểu thức ghép ngắn và rõ ràng:**

~~~java
String userName = "Lan";
int count = 3;
String message = "Hello " + userName + ", count=" + count;
System.out.println(message); // Hello Lan, count=3
~~~

Ở đây `+` đọc đơn giản và phù hợp. Sửa sang builder không nhất thiết tốt hơn về mặt rõ nghĩa.

**Nối sẵn danh sách bằng dấu phân cách:**

~~~java
String csv = String.join(",", "A", "B", "C");
System.out.println(csv); // A,B,C
~~~

**Định dạng theo mẫu:**

~~~java
String summary = String.format(
        java.util.Locale.ROOT, "count=%d, ratio=%.2f", 3, 0.5);
System.out.println(summary); // count=3, ratio=0.50
~~~

Khi cần định dạng số, căn lề, locale hay phần thập phân, `String.format` có thể phù hợp hơn hàng loạt lời gọi `append`.

**Lựa chọn theo ý định:**

| Tình huống | Thường nên chọn |
|---|---|
| Ghép 2–5 thành phần trong một câu lệnh | `+` |
| Nối các chuỗi sẵn có bằng dấu phân cách | `String.join` |
| Xây nội dung qua vòng lặp/nhánh, thêm nhiều lần | `StringBuilder` |
| Định dạng theo mẫu có quy tắc trình bày | `String.format` hoặc formatter thích hợp |

## 9. Ví dụ Java 17 hoàn chỉnh, chạy được

Lưu vào file đúng tên **`StringBuilderLoopDemo.java`**:

~~~java
public final class StringBuilderLoopDemo {
    private StringBuilderLoopDemo() {}

    static String joinNames(String[] names) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < names.length; i++) {
            if (i > 0) {
                builder.append(", ");
            }
            builder.append(names[i]);
        }
        return builder.toString();
    }

    static String withPlus(int count) {
        String result = "";
        for (int i = 1; i <= count; i++) {
            result += i;
        }
        return result;
    }

    static String withBuilder(int count) {
        StringBuilder builder = new StringBuilder();
        for (int i = 1; i <= count; i++) {
            builder.append(i);
        }
        return builder.toString();
    }

    public static void main(String[] args) {
        String[] names = {"Lan", "Minh", "An"};
        System.out.println("joined=" + joinNames(names));
        System.out.println("empty=<" + joinNames(new String[0]) + ">");
        System.out.println("plus=" + withPlus(5));
        System.out.println("builder loop=" + withBuilder(5));

        StringBuilder document = new StringBuilder("Java");
        document.append(' ').append(17).append('!');
        System.out.println("initial=" + document);
        document.setCharAt(0, 'j');
        document.insert(5, "Core ");
        System.out.println("inserted=" + document);
        document.delete(5, 10);
        System.out.println("deleted=" + document);

        String snapshot = document.toString();
        document.append(" again");
        System.out.println("snapshot=" + snapshot);
        System.out.println("changed=" + document);

        StringBuilder reserved = new StringBuilder(32);
        System.out.println("reserved length=" + reserved.length());
        System.out.println("reserved capacity=" + reserved.capacity());
        reserved.append("Hi");
        System.out.println("after append length=" + reserved.length());

        StringBuilder typed = new StringBuilder();
        typed.append("ok=").append(true)
                .append(", count=").append(3);
        System.out.println("typed=" + typed);
    }
}
~~~

**Yêu cầu:** JDK 17 hoặc mới hơn, terminal đặt trong thư mục chứa `StringBuilderLoopDemo.java`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StringBuilderLoopDemo.java
java -cp . StringBuilderLoopDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StringBuilderLoopDemo.java
java -cp . StringBuilderLoopDemo
~~~

**Expected output (chính xác):**

~~~text
joined=Lan, Minh, An
empty=<>
plus=12345
builder loop=12345
initial=Java 17!
inserted=java Core 17!
deleted=java 17!
snapshot=java 17!
changed=java 17! again
reserved length=0
reserved capacity=32
after append length=2
typed=ok=true, count=3
~~~

**Giải thích những dòng dễ nhầm:**

- `insert(5, "Core ")` chèn trước index 5 của `"java 17!"`, thành `"java Core 17!"`.
- `delete(5, 10)` xóa đoạn `[5, 10)`, trả nội dung về `"java 17!"`.
- `snapshot` giữ văn bản tại thời điểm `toString()`, không đổi khi builder được thêm `" again"`.
- `new StringBuilder(32)` có `capacity() == 32`, nhưng `length() == 0` trước khi `append`.
- Cả `withPlus(5)` và `withBuilder(5)` cho cùng văn bản; mục đích minh họa là **cấu trúc xây chuỗi**, không đo tốc độ.

Chương trình độc lập, không cần Maven, Gradle hay thư viện bên ngoài JDK.

## 10. Các lỗi thường gặp

| Cách làm / lỗi | Vì sao cần chú ý? | Hướng xử lý |
|---|---|---|
| `String s = ""; for (...) s += value;` | Có thể lặp lại cấp phát/copy khi tích lũy nội dung lớn | Tạo `StringBuilder` bên ngoài vòng lặp |
| `new StringBuilder()` bên trong mỗi lần lặp | Mất lợi ích tái sử dụng một builder | Khởi tạo một lần **trước** vòng lặp nếu mục tiêu là một kết quả |
| Quên `toString()` khi API yêu cầu `String` | `StringBuilder` và `String` là hai kiểu khác nhau | Trả `builder.toString()` |
| `builder = builder.append(x)` trong mọi vòng | Hợp lệ nhưng gán lại biến không cần thiết | Gọi `builder.append(x)` trực tiếp |
| Gọi `String.join` nhưng vẫn tự viết builder cho danh sách đơn giản | Tăng code không cần thiết | Dùng API sẵn có khi rõ ý |
| Quên phân cách giữa các phần tử | Kết quả dính vào nhau, khó đọc | Thêm `", "` theo chỉ số hoặc trạng thái |
| Dùng `capacity()` để lấy chiều dài nội dung | Capacity không phải length | Dùng `length()` |
| Nghĩ `final StringBuilder` không thể append | final khóa biến tham chiếu, không khóa object | Có thể append, không thể gán lại biến |
| Dùng `charAt`/ `delete` với index sai | Có thể gặp `IndexOutOfBoundsException` | Kiểm tra phạm vi theo `length()` |
| Coi index bằng số ký tự hiển thị | UTF-16 code unit có thể khác Unicode code point | Chọn API theo đơn vị Unicode cần xử lý |
| Chia sẻ builder mutable giữa nhiều thread | Không có đồng bộ nội tại | Giữ builder cục bộ một thread hoặc phối hợp đồng bộ |
| Dùng builder chung cho nhiều dữ liệu cần cách ly | Nội dung có thể bị thay đổi ngoài ý muốn | Tạo builder riêng theo mỗi tác vụ |

### Một bẫy Java dễ bỏ sót: append `null`

~~~java
StringBuilder builder = new StringBuilder();
builder.append((Object) null);
System.out.println(builder); // null
~~~

`append((Object) null)` thêm **bốn ký tự** `n`, `u`, `l`, `l`. Nhưng một số overload, đặc biệt với mảng ký tự null, có hành vi khác; khi dữ liệu có thể null, hãy chọn overload và chính sách hiển thị rõ ràng thay vì truyền giá trị null một cách mơ hồ.

## 11. Bài tập kèm đáp án

### Bài A — ghép số bằng builder

Tạo chuỗi `1-2-3-4` bằng vòng lặp.

**Đáp án:**

~~~java
StringBuilder b = new StringBuilder();
for (int i = 1; i <= 4; i++) {
    if (i > 1) {
        b.append('-');
    }
    b.append(i);
}
System.out.println(b.toString()); // 1-2-3-4
~~~

### Bài B — String snapshot

~~~java
StringBuilder b = new StringBuilder("A");
String snapshot = b.toString();
b.append('B');
System.out.println(snapshot);
System.out.println(b);
~~~

**Đáp án:**

~~~text
A
AB
~~~

Vì snapshot là String bất biến đã nhận từ builder trước khi thêm `B`.

### Bài C — length hay capacity?

~~~java
StringBuilder b = new StringBuilder(50);
b.append("Hi");
System.out.println(b.length());
System.out.println(b.capacity());
~~~

**Đáp án:**

~~~text
2
50
~~~

### Bài D — có cần builder không?

~~~java
String greeting = "Hello, " + name + "!";
~~~

**Đáp án:** thường **không cần** nếu chỉ ghép vài thành phần một lần. Đây là một biểu thức rõ ràng và compiler/JVM Java hiện đại có thể tối ưu. Hãy dùng builder khi có lý do như lặp nhiều lần hoặc xây dựng nhiều bước.

### Bài E — sửa phần tử của chuỗi đã chốt?

~~~java
StringBuilder builder = new StringBuilder("Java");
String s = builder.toString();
builder.setCharAt(0, 'K');
System.out.println(s);
System.out.println(builder);
~~~

**Đáp án:**

~~~text
Java
Kava
~~~

## 12. Checklist tự đánh giá

- [ ] Hiểu vì sao `String += value` lặp nhiều lần có thể tốn chi phí.
- [ ] Biết tạo `StringBuilder` **một lần trước vòng lặp**.
- [ ] Dùng `append` để thêm giá trị và `toString()` để lấy String cuối.
- [ ] Hiểu `StringBuilder` mutable, `String` immutable và snapshot không tự thay đổi.
- [ ] Biết thêm dấu phân cách không thừa ở đầu/cuối.
- [ ] Phân biệt `length()` và `capacity()`; hiểu constructor nhận capacity.
- [ ] Nắm các method cơ bản `append`, `insert`, `delete`, `setCharAt`.
- [ ] Chọn `+` hoặc `String.join` khi đơn giản hơn.
- [ ] Nhận biết chỉ số thao tác ký tự theo UTF-16 code units.
- [ ] Không chia sẻ mutable builder không kiểm soát giữa các luồng.
- [ ] Biên dịch và chạy `StringBuilderLoopDemo.java` bằng JDK 17+, so với expected output.

**Kết luận:** `StringBuilder` hữu ích khi phải **ghép chuỗi lặp lại hoặc xây nội dung qua nhiều bước**, bởi nó cập nhật một bộ dựng mutable bằng `append` rồi tạo `String` cuối qua `toString()`. Dùng đúng nơi sẽ giúp code rõ ý và thường giảm chi phí tạo chuỗi trung gian; với vài phép nối ngắn, `+` vẫn là lựa chọn dễ đọc và hợp lý.