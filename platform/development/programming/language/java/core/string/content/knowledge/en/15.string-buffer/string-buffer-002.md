# So sánh API của StringBuffer và StringBuilder trong Java

`StringBuffer` và `StringBuilder` đều là lớp dùng để **xây dựng và chỉnh sửa chuỗi ký tự có thể thay đổi** (*mutable character sequences*). Chúng có gần như cùng bộ API: `append`, `insert`, `delete`, `replace`, `reverse`, `charAt`, `setCharAt`, `length`, `capacity`, `substring` và nhiều phương thức hỗ trợ Unicode. Điểm khác biệt thiết kế quan trọng nhất là: **StringBuffer đồng bộ hóa các thao tác cần thiết trên chính đối tượng**, còn **StringBuilder không thực hiện đồng bộ hóa nội bộ**.

Vì thế, trong mã chỉ có một luồng thao tác trên một bộ dựng chuỗi, `StringBuilder` thường là lựa chọn phù hợp và có thể tránh chi phí đồng bộ hóa. Khi một đối tượng dựng chuỗi thật sự được **chia sẻ để nhiều luồng cùng sửa**, `StringBuffer` có thể phù hợp hơn vì các thao tác riêng lẻ được đồng bộ hóa. Tuy nhiên, đồng bộ từng lời gọi **không biến mọi chuỗi nhiều lời gọi thành một giao dịch nguyên tử**.

Bài này tập trung vào việc đối chiếu **API**, cách dùng, kết quả trả về, hiệu năng và giới hạn thread-safety — không coi hai lớp là thay thế cho `String` bất biến trong mọi trường hợp.

## 1. Bức tranh tổng quan: giống gì, khác gì?

| Tiêu chí | `StringBuilder` | `StringBuffer` |
|---|---|---|
| Mục đích | Xây dựng/chỉnh sửa chuỗi có thể thay đổi | Xây dựng/chỉnh sửa chuỗi có thể thay đổi |
| Có thay đổi nội dung tại chỗ? | Có | Có |
| Đồng bộ hóa phương thức nội bộ | Không | Có, với các thao tác cần thiết trên buffer |
| Sử dụng khi | Builder cục bộ, một luồng sở hữu, hoặc tự quản lý đồng bộ | Cùng một buffer được chia sẻ và có các thao tác đồng thời |
| `append`, `insert`, `delete`, `replace` | Có | Có |
| `reverse`, `setCharAt`, `setLength` | Có | Có |
| `length`, `capacity`, `ensureCapacity` | Có | Có |
| `charAt`, `codePointAt`, `appendCodePoint` | Có | Có |
| `substring`, `subSequence`, `indexOf` | Có | Có |
| `toString()` | Trả một `String` chứa nội dung hiện tại | Trả một `String` chứa nội dung hiện tại |
| Kiểu trả về của `append(...)` | `StringBuilder` | `StringBuffer` |
| Thường được ưu tiên khi không cần đồng bộ | Có | Ít cần thiết hơn |

Cả hai đều triển khai các giao diện hữu ích như `CharSequence` và `Appendable`; cả hai không thay đổi nội dung của một đối tượng `String` đã tạo ra trước đó. Chúng **không phải lớp con của nhau**: bạn không thể ép kiểu trực tiếp một `StringBuilder` thành `StringBuffer`, hoặc ngược lại.

Mặc dù tên và chữ ký phương thức tương tự, tính đồng bộ hóa quyết định việc chọn lớp trong chương trình đa luồng. `StringBuffer` không mặc nhiên nhanh hơn, còn `StringBuilder` cũng không mặc nhiên sai trong ứng dụng nhiều luồng: một builder **thuộc riêng một luồng hoặc một lần gọi** vẫn dùng an toàn mà không cần chia sẻ.

## 2. Khởi tạo và quản lý length/capacity

Hai lớp đều có các cách tạo thường dùng:

```java
StringBuilder a = new StringBuilder();
StringBuilder b = new StringBuilder(64);
StringBuilder c = new StringBuilder("Java");

StringBuffer x = new StringBuffer();
StringBuffer y = new StringBuffer(64);
StringBuffer z = new StringBuffer("Java");
```

Đây là **đoạn mã minh họa**, không phải tệp chương trình độc lập. Các constructor không tham số tạo buffer ban đầu rỗng; constructor nhận `int` đặt dung lượng ban đầu; constructor nhận `String` tạo buffer có sẵn nội dung.

Hai khái niệm dễ nhầm:

- `length()` là **số code unit UTF-16 đang có trong nội dung**.
- `capacity()` là **dung lượng code unit mà bộ dựng hiện có thể chứa trước khi cần mở rộng**, và luôn không nhỏ hơn `length()`.
- `ensureCapacity(minimumCapacity)` yêu cầu khả năng chứa tối thiểu, **không thêm ký tự** và không làm tăng `length()`.
- `trimToSize()` yêu cầu cố gắng tiết kiệm dung lượng dư. Không dựa vào việc `capacity()` phải bằng `length()` trong mọi triển khai sau lời gọi.

Ví dụ: `new StringBuilder(8)` và `new StringBuffer(8)` ban đầu đều có `length() == 0`, `capacity() == 8`. `append("Java")` biến `length()` thành 4 nhưng chưa cần thay `capacity()`. Cả hai đều làm việc theo **code unit UTF-16**, không phải số grapheme cluster hay số byte UTF-8.

### Ví dụ chạy được: constructor, length và capacity

Lưu dưới tên **`BuilderBufferCapacityDemo.java`**:

```java
public class BuilderBufferCapacityDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(8);
        StringBuffer buffer = new StringBuffer(8);

        builder.append("Java");
        buffer.append("Java");

        System.out.println("builder text: " + builder);
        System.out.println("buffer text: " + buffer);
        System.out.println("builder length: " + builder.length());
        System.out.println("buffer length: " + buffer.length());
        System.out.println("builder capacity: " + builder.capacity());
        System.out.println("buffer capacity: " + buffer.capacity());

        builder.ensureCapacity(8);
        buffer.ensureCapacity(8);
        System.out.println("builder still length 4: "
                + (builder.length() == 4));
        System.out.println("buffer still length 4: "
                + (buffer.length() == 4));
    }
}
```

Chạy với JDK 17+:

```bash
javac BuilderBufferCapacityDemo.java
java BuilderBufferCapacityDemo
```

**Stdout:**

```text
builder text: Java
buffer text: Java
builder length: 4
buffer length: 4
builder capacity: 8
buffer capacity: 8
builder still length 4: true
buffer still length 4: true
```

Trong ví dụ, dung lượng ban đầu đủ cho bốn ký tự nên `capacity()` vẫn là 8. Không suy ra quy luật nhân đôi cụ thể cho mọi lần mở rộng hoặc mọi phiên bản JVM: hợp đồng API bảo đảm điều kiện dung lượng cần thiết, còn chiến lược cấp phát là chi tiết triển khai.

## 3. Đối chiếu các nhóm API thường dùng

### 3.1. Thêm nội dung: `append`

Cả hai có các overload thêm `String`, `char`, số nguyên, số thực, boolean, mảng `char[]`, `CharSequence`, một phần của `CharSequence` và code point. Điểm cần nhớ: overload được chọn theo **kiểu đối số**, không theo ý định hiển thị của người viết.

```java
new StringBuilder().append(65);            // "65", không phải "A"
new StringBuffer().append(65);             // "65", không phải "A"
new StringBuilder().append('A');           // "A"
new StringBuffer().append('A');            // "A"
new StringBuilder().appendCodePoint(65);   // "A"
new StringBuffer().appendCodePoint(65);    // "A"
```

Đây là những **biểu thức minh họa**. Giá trị `int` trong `append(65)` được chuyển thành chữ số thập phân; để thêm code point `U+0041`, hãy gọi `appendCodePoint(65)` hoặc dùng `char` `'A'` nếu chỉ cần code unit BMP phù hợp.

Các phương thức `append(...)` của từng lớp trả về **chính đối tượng nhận lời gọi**, nên có thể viết kiểu fluent:

```java
StringBuilder builder = new StringBuilder()
        .append("Hello")
        .append(' ')
        .append("Java");

StringBuffer buffer = new StringBuffer()
        .append("Hello")
        .append(' ')
        .append("Java");
```

### 3.2. Chèn, xóa, thay thế và đảo nội dung

| Thao tác | API ở cả hai lớp | Cách hiểu |
|---|---|---|
| Chèn trước vị trí | `insert(offset, value)` | Chèn tại offset UTF-16 |
| Xóa đoạn | `delete(start, end)` | Xóa phạm vi `[start, end)` |
| Xóa một code unit | `deleteCharAt(index)` | Xóa đúng một `char` UTF-16 |
| Thay đoạn | `replace(start, end, str)` | Thay phạm vi bằng chuỗi mới |
| Đảo nội dung | `reverse()` | Đảo dãy nội dung, có xử lý đặc biệt cho surrogate pair |
| Thay một code unit | `setCharAt(index, ch)` | Sửa một `char` tại vị trí đã có |
| Điều chỉnh chiều dài | `setLength(newLength)` | Cắt bớt hoặc thêm code unit `'\u0000'` |

Mọi offset trong bảng nói trên được xác định theo **code unit UTF-16**. Vì thế, `deleteCharAt(i)` hay `setCharAt(i, ch)` có thể phá cặp surrogate nếu chọn sai vị trí với emoji. `reverse()` cố gắng giữ cặp surrogate hợp lệ, nhưng không có nghĩa đảo đúng mọi cụm ký tự hiển thị có nhiều code point (như chữ và dấu kết hợp).

### 3.3. Đọc nội dung, tìm kiếm và cắt chuỗi

| Tác vụ | API tương ứng |
|---|---|
| Đọc một code unit | `charAt(index)` |
| Đọc code point tại offset UTF-16 | `codePointAt(index)` |
| Đọc code point trước offset | `codePointBefore(index)` |
| Đếm code point theo khoảng UTF-16 | `codePointCount(begin, end)` |
| Di chuyển offset theo số code point | `offsetByCodePoints(index, offset)` |
| Sao chép ký tự vào mảng | `getChars(srcBegin, srcEnd, dst, dstBegin)` |
| Tìm lần xuất hiện đầu | `indexOf(str)`, `indexOf(str, fromIndex)` |
| Tìm lần xuất hiện cuối | `lastIndexOf(str)`, `lastIndexOf(str, fromIndex)` |
| Lấy chuỗi con | `substring(start)`, `substring(start, end)` |
| Lấy dưới giao diện `CharSequence` | `subSequence(start, end)` |
| Tạo `String` chứa nội dung hiện tại | `toString()` |

`indexOf` và `lastIndexOf` trả `-1` nếu không tìm thấy. `substring(start, end)` hợp lệ khi `0 <= start <= end <= length()`; tham số kết thúc là **exclusive**. Không vì một builder/buffer mutable mà ranh giới được nới lỏng.

### 3.4. Các thao tác trả về builder/buffer hay giá trị khác?

- `append`, `insert`, `delete`, `deleteCharAt`, `replace`, `reverse` và `appendCodePoint` thường trả **đúng kiểu bộ dựng đang dùng**, giúp nối phương thức.
- `setCharAt`, `setLength`, `ensureCapacity` và `trimToSize` trả `void`; không thể tiếp tục chain sau chúng.
- `charAt` trả `char`; `codePointAt` trả `int`; `length` và `capacity` trả `int`.
- `substring` trả `String`, không trả `StringBuilder` hoặc `StringBuffer`.
- `toString()` trả `String`, là một đối tượng có nội dung bất biến; thay đổi bộ dựng sau đó không thay đổi nội dung đã nhận.

Đây là những khác biệt kiểu trả về cần biết khi chuyển mã từ lớp này sang lớp kia: tên phương thức giữ nguyên nhưng kiểu receiver và kiểu kết quả builder/buffer là khác nhau.

## 4. Ví dụ dùng song song cùng một chuỗi lời gọi API

Lưu thành **`BuilderBufferApiDemo.java`**:

```java
public class BuilderBufferApiDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        StringBuffer buffer = new StringBuffer("Java");

        builder.append(" Core").insert(4, " 17").delete(4, 7);
        buffer.append(" Core").insert(4, " 17").delete(4, 7);

        builder.replace(5, 9, "SE");
        buffer.replace(5, 9, "SE");

        System.out.println("builder: " + builder);
        System.out.println("buffer: " + buffer);
        System.out.println("same content: "
                + builder.toString().contentEquals(buffer));

        System.out.println("builder first char: " + builder.charAt(0));
        System.out.println("buffer first char: " + buffer.charAt(0));
        System.out.println("builder substring: " + builder.substring(5));
        System.out.println("buffer substring: " + buffer.substring(5));

        builder.setCharAt(0, 'j');
        buffer.setCharAt(0, 'j');
        System.out.println("after setCharAt: "
                + builder + " | " + buffer);
    }
}
```

```bash
javac BuilderBufferApiDemo.java
java BuilderBufferApiDemo
```

**Stdout:**

```text
builder: Java SE
buffer: Java SE
same content: true
builder first char: J
buffer first char: J
builder substring: SE
buffer substring: SE
after setCharAt: java SE | java SE
```

Giải thích các bước:

1. `append(" Core")` tạo `"Java Core"`.
2. `insert(4, " 17")` tạo `"Java 17 Core"`, rồi `delete(4, 7)` xóa đúng `" 17"` để trở lại `"Java Core"`.
3. `replace(5, 9, "SE")` thay `"Core"` bằng `"SE"` để được `"Java SE"`.
4. Các phương thức ở hai lớp có cùng cách hiểu vị trí và nội dung.
5. `setCharAt(0, 'j')` sửa một code unit ở đầu, cho `"java SE"`.
6. `contentEquals(buffer)` so **nội dung `String`** bên trái với `CharSequence` bên phải; việc hai builder/buffer có kiểu khác nhau không ngăn so nội dung bằng API phù hợp.

Ví dụ là thao tác tuần tự một luồng; nó minh họa **tương đồng API**, không chứng minh tốc độ hay an toàn khi nhiều luồng cùng thao tác.

## 5. Khác biệt ở hợp đồng đồng bộ

Hai lớp có gần như cùng API dựng ký tự, nhưng `StringBuffer` đồng bộ những thao tác cần thiết trên **monitor của đối tượng đích**, còn `StringBuilder` không tự cung cấp khóa. Khi dùng chung một `StringBuffer`, mỗi lần `append` hoặc `insert` được bảo vệ riêng; thứ tự giữa các lần gọi của những luồng khác nhau phụ thuộc lịch chạy.

Một tham số `CharSequence` mutable là trạng thái **nguồn**, không tự được bảo vệ bởi monitor của buffer đích. Nếu cần nội dung nguồn ổn định, hãy kiểm soát writer hoặc chuyển nó thành `String` bất biến trước khi gọi.

```java
StringBuffer shared = new StringBuffer();
shared.append("A"); // Lần gọi thứ nhất kết thúc và nhả monitor.
shared.append("B"); // Luồng khác có thể append ở giữa.
```

Trong mã đa luồng, một `StringBuilder` cục bộ vẫn an toàn khi không bị chia sẻ; không có quy tắc nào yêu cầu mọi chương trình đa luồng phải dùng `StringBuffer`. Bài mở đầu **“Vai trò của StringBuffer trong mã cần đồng bộ”** có ví dụ quan sát số ký tự từ nhiều luồng.

## 6. Ranh giới API khi thao tác nhiều bước

Nếu muốn “chỉ append khi chưa vượt `maxLength`” hoặc “ba phần của bản ghi phải liền nhau”, đây là một **thao tác logic nhiều bước** vượt quá hợp đồng từng phương thức. Có thể khóa toàn bộ vùng kiểm tra–sửa với `synchronized (buffer)`, hoặc dựng trọn `String record` rồi `buffer.append(record)` đúng một lần nếu không cần kiểm tra trạng thái khác.

Hai bài riêng **“Đồng bộ từng phương thức không bảo đảm nguyên tử cho cả chuỗi thao tác”** và **“Chọn khóa chung khi cần phối hợp nhiều thao tác”** hướng dẫn cách tái hiện race, xác định invariant và chọn monitor. Ở đây, khi so API, điều cần giữ là **tên phương thức tương đương không đồng nghĩa phạm vi đồng bộ của nhiều lời gọi cũng tương đương**.


## 7. Lưu ý về tham chiếu, `toString` và `equals`

Cả hai lớp là đối tượng mutable, khác `String` bất biến. Sau khi gọi `toString()`, bạn có giá trị `String` độc lập về nội dung: những lần sửa buffer/builder tiếp theo không sửa đối tượng `String` đã thu được.

### Ví dụ chụp nội dung thành String

**`BufferSnapshotDemo.java`**

```java
public class BufferSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        StringBuffer buffer = new StringBuffer("A");

        String builderSnapshot = builder.toString();
        String bufferSnapshot = buffer.toString();

        builder.append("B");
        buffer.append("B");

        System.out.println("builder now: " + builder);
        System.out.println("builder snapshot: " + builderSnapshot);
        System.out.println("buffer now: " + buffer);
        System.out.println("buffer snapshot: " + bufferSnapshot);

        System.out.println("builder.equals(new builder): "
                + builder.equals(new StringBuilder("AB")));
        System.out.println("buffer.equals(new buffer): "
                + buffer.equals(new StringBuffer("AB")));
        System.out.println("snapshots equal: "
                + builderSnapshot.equals(bufferSnapshot));
    }
}
```

```bash
javac BufferSnapshotDemo.java
java BufferSnapshotDemo
```

**Stdout:**

```text
builder now: AB
builder snapshot: A
buffer now: AB
buffer snapshot: A
builder.equals(new builder): false
buffer.equals(new buffer): false
snapshots equal: true
```

`StringBuilder` và `StringBuffer` **không override `Object.equals()` để so nội dung**. Hai instance khác nhau, dù chứa cùng chữ, thường có `equals(...) == false`. Muốn so nội dung:

- Dùng `builder.toString().equals(buffer.toString())` nếu muốn snapshot thành hai chuỗi bất biến và so chúng.
- Dùng `String.contentEquals(CharSequence)` để so nội dung `String` với `StringBuilder`/`StringBuffer` theo API.
- Nếu nguồn đang bị sửa đồng thời, phải xác định chính sách snapshot và đồng bộ thích hợp; hai lần gọi `toString()` trên hai đối tượng khác nhau **không tự thành một snapshot nguyên tử xuyên cả hai**.

Không sử dụng `==` để so nội dung chuỗi: `==` giữa các đối tượng tham chiếu hỏi chúng có cùng một instance hay không.

## 8. Khác biệt về kiểu trả về khi chuyển đổi mã

Hai lớp có tên phương thức gần giống, nhưng mỗi lớp trả về đúng kiểu cụ thể của mình ở các API fluent:

```java
StringBuilder sb = new StringBuilder().append("A").reverse();
StringBuffer bf = new StringBuffer().append("A").reverse();
```

Nếu hàm hiện viết:

```java
static StringBuilder appendTag(StringBuilder target, String tag) {
    return target.append(tag);
}
```

thì không thể truyền một `StringBuffer` vào mà không thay chữ ký. Đây là **đoạn minh họa chữ ký**, không phải chương trình độc lập. Có thể thiết kế hàm tổng quát theo `Appendable` khi chỉ cần append mà không cần API riêng của hai lớp:

```java
static void appendTag(Appendable target, String tag)
        throws java.io.IOException {
    target.append(tag);
}
```

`Appendable` khai báo `append` có thể ném `IOException`; vì thế chữ ký tổng quát phải xử lý ngoại lệ kiểm tra (*checked exception*) ở giao diện, dù hai hiện thực cụ thể `StringBuilder` và `StringBuffer` không ném `IOException` trong các overload tương ứng. Đổi sang `Appendable` cũng mất quyền gọi trực tiếp `delete`, `capacity`, `reverse` hoặc `setCharAt` vì các phương thức này không thuộc giao diện.

Nếu chỉ cần **đọc** dãy ký tự, `CharSequence` là giao diện thích hợp hơn; nhưng một `CharSequence` mutable có thể thay đổi sau khi được chuyển vào hàm, nên không xem nó mặc nhiên bất biến.

### Ví dụ tổng quát qua `Appendable`

**`AppendableCompatibilityDemo.java`**

```java
import java.io.IOException;

public class AppendableCompatibilityDemo {
    private static void addLabel(Appendable out, String value)
            throws IOException {
        out.append('[').append(value).append(']');
    }

    public static void main(String[] args) throws IOException {
        StringBuilder builder = new StringBuilder();
        StringBuffer buffer = new StringBuffer();

        addLabel(builder, "A");
        addLabel(buffer, "A");

        System.out.println(builder.toString());
        System.out.println(buffer.toString());
    }
}
```

```bash
javac AppendableCompatibilityDemo.java
java AppendableCompatibilityDemo
```

**Stdout:**

```text
[A]
[A]
```

Dùng giao diện giúp mã nguồn không phụ thuộc lớp cụ thể khi chỉ cần chức năng chung. Nhưng **nó không quyết định thread-safety**: nếu đầu vào là `StringBuilder` chung giữa các luồng, lời gọi thông qua `Appendable` không làm cho builder đó tự động được đồng bộ hóa.

## 9. Unicode và chỉ số: hai lớp có cùng rủi ro

Vì cả hai lưu nội dung theo ngữ nghĩa UTF-16:

- `length()` và các chỉ số `charAt`, `insert`, `delete`, `replace`, `substring` đều làm việc theo **code unit UTF-16**.
- `appendCodePoint(int)` là API thêm một code point, có thể tạo **một** code unit trong BMP hoặc **hai** code unit ngoài BMP.
- `codePointAt` và `codePointCount` giúp xử lý dữ liệu theo Unicode code point, nhưng không đếm **grapheme cluster**.
- `deleteCharAt` có thể cắt đôi surrogate pair; phải chọn ranh giới bằng `offsetByCodePoints` hoặc công cụ phân đoạn grapheme nếu mục tiêu là ký tự người dùng nhìn thấy.
- `reverse()` có xử lý surrogate pair, nhưng không bảo đảm đảo đúng cụm ký tự chứa nhiều code point.

**`BuilderBufferUnicodeDemo.java`**

```java
public class BuilderBufferUnicodeDemo {
    public static void main(String[] args) {
        int smile = 0x1F60A;

        StringBuilder builder = new StringBuilder()
                .appendCodePoint(smile).append('A');
        StringBuffer buffer = new StringBuffer()
                .appendCodePoint(smile).append('A');

        System.out.println("builder units: " + builder.length());
        System.out.println("buffer units: " + buffer.length());
        System.out.println("builder points: "
                + builder.codePointCount(0, builder.length()));
        System.out.println("buffer points: "
                + buffer.codePointCount(0, buffer.length()));

        System.out.println("same Unicode content: "
                + builder.toString().contentEquals(buffer));

        System.out.printf("builder first code point: U+%X%n",
                builder.codePointAt(0));
        System.out.printf("buffer first code point: U+%X%n",
                buffer.codePointAt(0));
    }
}
```

```bash
javac BuilderBufferUnicodeDemo.java
java BuilderBufferUnicodeDemo
```

**Stdout:**

```text
builder units: 3
buffer units: 3
builder points: 2
buffer points: 2
same Unicode content: true
builder first code point: U+1F60A
buffer first code point: U+1F60A
```

Khi thêm emoji 😊 (một supplementary code point) và chữ `A` (một BMP code point), mỗi bộ dựng chứa **3 code unit UTF-16** nhưng chỉ có **2 code point**. Cả hai lớp cho kết quả giống nhau. Việc StringBuffer đồng bộ hóa phương thức không tự sửa các lỗi logic Unicode nếu chương trình chọn điểm cắt sai.

## 10. Hiệu năng đi theo cách sử dụng API

`StringBuilder` tránh đồng bộ nội bộ khi chỉ một luồng sở hữu bộ dựng; `StringBuffer` có thêm cơ chế monitor khi bảo vệ buffer dùng chung. Nhưng một phép đo đơn giản không đủ để khẳng định một tỷ lệ chênh lệch cố định, vì kết quả phụ thuộc JDK/JIT, cấp phát, dung lượng và tranh chấp khóa.

Hãy chọn theo **quyền sở hữu instance và tính đúng của chương trình** trước. Khi có nhu cầu tối ưu, so sánh hai phương án có cùng ngữ nghĩa; xem xét việc dựng từng phần cục bộ rồi append theo lô để giảm số lần các luồng cùng đi vào monitor. Bài **“Chi phí đồng bộ và điều kiện thực sự cần StringBuffer”** hướng dẫn thiết kế phép đo JMH và phân tích contention.


## 11. Các lỗi thường gặp khi so sánh API

| Nhầm lẫn | Vấn đề thực tế | Cách hiểu đúng |
|---|---|---|
| “StringBuffer và StringBuilder có nội dung giống nhau nên `equals` trả true” | Hai lớp không override `equals` để so nội dung | Dùng `toString().equals(...)` hoặc `String.contentEquals(...)` |
| “StringBuffer bảo đảm cả đoạn kiểm tra rồi append là nguyên tử” | Mỗi lời gọi riêng biệt không tạo một giao dịch nhiều bước | Dùng một khóa chung bảo vệ toàn bộ bất biến |
| “Chỉ có ứng dụng một luồng mới được dùng StringBuilder” | Các builder cục bộ không bị chia sẻ vẫn an toàn trong ứng dụng đa luồng | Xét **quyền sở hữu instance**, không chỉ số luồng của ứng dụng |
| “`append(int)` thêm code point Unicode” | `append(int)` thêm biểu diễn thập phân của số | Dùng `appendCodePoint(int)` |
| “`length()` đếm ký tự hiển thị” | UTF-16 có surrogate pair; grapheme có thể gồm nhiều code point | Phân biệt units, points và clusters |
| “`capacity()` là số phần tử đã thêm” | Capacity là khả năng chứa, không phải length | Dùng `length()` để biết số code unit hiện có |
| “`substring` trả builder mới” | Trả `String` | Dùng `StringBuilder`/`StringBuffer` mới nếu cần tiếp tục sửa |
| “Có thể ép kiểu StringBuilder ↔ StringBuffer” | Không có quan hệ kế thừa giữa hai lớp | Tạo đối tượng mới từ nội dung, hoặc thiết kế theo giao diện |
| “`toString()` sẽ phản ánh mọi thay đổi về sau” | `String` kết quả là bất biến | Chụp lại `toString()` nếu cần snapshot mới |
| “Khai báo tham số `Appendable` làm mọi thứ thread-safe” | Thread-safety vẫn phụ thuộc instance và chính sách đồng bộ | Kiểm soát chia sẻ và quyền sở hữu |
| “Mọi phương thức có tên giống nhau đều dùng tham số và kết quả như nhau 100%” | Return type fluent là loại bộ dựng cụ thể; API trong JDK có thể tiến hóa | Kiểm tra chữ ký và phiên bản JDK của ứng dụng |

## 12. Tự kiểm tra kiến thức

Trước khi chạy, dự đoán stdout:

**`BuilderBufferSelfCheck.java`**

```java
public class BuilderBufferSelfCheck {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("ab");
        StringBuffer buffer = new StringBuffer("ab");

        builder.append('c').reverse();
        buffer.append('c').reverse();

        System.out.println(builder);
        System.out.println(buffer);
        System.out.println(builder.length() == buffer.length());
        System.out.println(builder.toString().equals(buffer.toString()));

        String snapshot = buffer.toString();
        buffer.append('!');
        System.out.println(snapshot);
        System.out.println(buffer);

        System.out.println(new StringBuffer("ab")
                .equals(new StringBuffer("ab")));
    }
}
```

```bash
javac BuilderBufferSelfCheck.java
java BuilderBufferSelfCheck
```

**Stdout:**

```text
cba
cba
true
true
cba
cba!
false
```

- `append('c')` nối `c` vào chuỗi `ab`, sau đó `reverse()` tạo `cba` trong từng đối tượng.
- Hai đối tượng chứa cùng nội dung và cùng độ dài, nhưng so bằng `toString().equals(...)` mới là so **giá trị văn bản**.
- `snapshot` vẫn là `"cba"` sau khi buffer đổi thành `"cba!"`, vì đó là một `String` bất biến.
- Hai `new StringBuffer("ab")` là hai instance khác nhau; `equals` không có phép so nội dung riêng nên trả `false`.

**Ba câu hỏi quyết định khi viết mã:**

1. Đối tượng dựng chuỗi có **được chia sẻ** qua các luồng không, hay mỗi luồng sở hữu riêng?
2. Nhu cầu chỉ là các lời gọi độc lập (`append`, `insert`, `delete`) hay có **bất biến nhiều bước** cần bảo vệ nguyên tử?
3. Mục tiêu là xử lý **nội dung ký tự**, **offset UTF-16**, hay **tham chiếu đối tượng**? Đã chọn đúng `equals`/`contentEquals`/`substring` hay chưa?

**Kết luận:** `StringBuilder` và `StringBuffer` gần như tương đương về bộ thao tác xây dựng chuỗi, nhưng khác nhau về cơ chế đồng bộ hóa. Chọn `StringBuilder` cho bộ dựng không bị chia sẻ đồng thời; chọn `StringBuffer` hoặc cơ chế đồng bộ khác khi có truy cập chung thực sự, và bảo vệ thêm các thao tác nhiều bước nếu nghiệp vụ yêu cầu. Dù dùng lớp nào, hãy luôn phân biệt nội dung với tham chiếu, length với capacity và code unit với code point để có kết quả đúng.
