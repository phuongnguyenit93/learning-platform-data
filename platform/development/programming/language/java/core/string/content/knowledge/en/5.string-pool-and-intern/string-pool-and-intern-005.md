# String.intern và tham chiếu chuẩn hóa theo nội dung

Trong Java, hai đối tượng `String` có thể chứa **cùng nội dung** nhưng mang **hai tham chiếu khác nhau**. Phương thức `String.intern()` giải quyết một nhu cầu riêng: lấy **tham chiếu chuẩn dùng chung cho cùng nội dung chuỗi** từ *string pool*. Nhờ vậy, khi hai chuỗi đã được intern và có nội dung bằng nhau, kết quả `intern()` của chúng tham chiếu đến **cùng một đối tượng**.

Từ “chuẩn hóa” trong bài này có nghĩa là **chuẩn hóa tham chiếu theo nội dung (canonicalization)**; nó **không** có nghĩa tự chuẩn hóa chữ hoa/chữ thường, khoảng trắng hoặc Unicode (NFC/NFD). Để viết chương trình đúng, cần tách rõ ba thao tác: **tạo hoặc giữ đối tượng `String`**, **so nội dung bằng `equals()`**, và **lấy tham chiếu từ pool bằng `intern()`**.

## 1. Nội dung chuỗi và định danh đối tượng khác nhau

Ví dụ:

```java
String a = new String("Java");
String b = new String("Java");
```

Mỗi biểu thức `new String("Java")` tạo một **đối tượng `String` mới**, nên `a` và `b` là hai tham chiếu khác nhau, dù nội dung giống hệt:

```text
a ──────> String #1 ── nội dung "Java"
b ──────> String #2 ── nội dung "Java"
```

- `a.equals(b)` trả `true` vì `String.equals()` kiểm tra cùng dãy ký tự.
- `a == b` trả `false` vì `==` giữa hai biến kiểu tham chiếu hỏi chúng có trỏ đến **cùng đối tượng** hay không.
- Cả hai đối tượng đều **immutable**: nội dung `String` không bị sửa sau khi đối tượng hình thành. Bất biến nội dung không đồng nghĩa mọi chuỗi bằng nhau đều là một đối tượng.

Ngược lại:

```java
String x = "Java";
String y = x;
```

`y = x` chỉ sao chép giá trị **tham chiếu**, vì vậy `x == y` là `true`. Hiện tượng này không cần `intern()`: cả hai biến trỏ đến một đối tượng ngay từ phép gán.

## 2. String pool và hợp đồng của `intern()`

*String pool* là kho do lớp `String` quản lý để các chuỗi cùng nội dung có thể dùng chung một đối tượng chuẩn. Đây là cơ chế liên quan đến **định danh tham chiếu**, không thay đổi quy tắc so nội dung của `String.equals()`.

Với biến không null `s`, lời gọi:

```java
String canonical = s.intern();
```

có ý nghĩa:

1. Nếu pool đã có một `String` có nội dung `equals(s)`, `intern()` trả về **tham chiếu đến đối tượng đã có trong pool**.
2. Nếu chưa có, pool ghi nhận chính đối tượng `s` làm đại diện chuẩn và trả về tham chiếu của nó, theo hợp đồng `String.intern()`.
3. Sau đó, các lời gọi `intern()` trên chuỗi khác nhưng **cùng nội dung** sẽ nhận cùng tham chiếu chuẩn, miễn các đối tượng và nội dung được xét theo hợp đồng Java.

Đặc tính cốt lõi cho hai chuỗi **không null** `s` và `t`:

```java
s.intern() == t.intern()
```

có cùng giá trị logic với:

```java
s.equals(t)
```

Đây chính là bảo đảm cần hiểu: **nội dung bằng nhau ⇒ kết quả intern có cùng tham chiếu**; nội dung khác nhau ⇒ kết quả intern không cùng đối tượng. Không cần (và không nên) dựa vào địa chỉ bộ nhớ, thứ tự cấp phát hoặc cách JVM triển khai pool để dùng hợp đồng này.

### Sơ đồ khái niệm

Giả sử pool đã có chuỗi `"Java"`:

```text
a ────────> String #1: "Java" (ngoài đối tượng chuẩn)
                            \
                             \ a.intern()
                              v
String pool ["Java"] ──────> String chuẩn: "Java"
                              ^
                             / b.intern()
                            /
b ────────> String #2: "Java" (ngoài đối tượng chuẩn)
```

Hai lời gọi `a.intern()` và `b.intern()` dẫn tới **cùng đối tượng chuẩn**. Tuy nhiên, lời gọi **không tự gán lại** biến `a` hay `b`. Muốn một biến giữ tham chiếu chuẩn, phải dùng kết quả: `a = a.intern();`.

### Điều gì không được suy ra?

- `s.intern()` **không nhất thiết** trả đối tượng khác `s`. Nếu chính `s` được chọn làm đại diện chuẩn (hoặc đã là đại diện chuẩn), có thể có `s == s.intern()`. Ngược lại, khi pool đã có đại diện khác, biểu thức đó có thể là `false`.
- `intern()` không sửa nội dung của `s` và không “hợp nhất” tất cả các biến đang giữ các đối tượng khác nhau.
- Hai đối tượng `String` được tạo độc lập không trở thành cùng đối tượng chỉ vì cùng gọi `equals()`. `equals()` là phép kiểm tra nội dung, không đổi tham chiếu.
- `intern()` là phương thức của đối tượng; gọi qua `null` sẽ gây `NullPointerException`.

## 3. Ví dụ hoàn chỉnh: intern trả đối tượng chuẩn, biến cũ vẫn giữ nguyên

Lưu mã dưới tên **`InternReferenceDemo.java`**:

```java
public class InternReferenceDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String fromNew = new String("Java");
        String fromBuilder = new StringBuilder()
                .append("Ja")
                .append("va")
                .toString();

        String canonical = fromBuilder.intern();

        System.out.println("new == literal: " + (fromNew == literal));
        System.out.println("new.equals(literal): " + fromNew.equals(literal));
        System.out.println("new.intern == literal: "
                + (fromNew.intern() == literal));

        System.out.println("builder == literal: "
                + (fromBuilder == literal));
        System.out.println("builder == canonical: "
                + (fromBuilder == canonical));
        System.out.println("canonical == literal: "
                + (canonical == literal));
        System.out.println("builder.equals(canonical): "
                + fromBuilder.equals(canonical));

        fromBuilder = fromBuilder.intern();
        System.out.println("builder after assignment == literal: "
                + (fromBuilder == literal));
    }
}
```

Tại thư mục có tệp, dùng JDK 17+:

```bash
javac InternReferenceDemo.java
java InternReferenceDemo
```

**Stdout:**

```text
new == literal: false
new.equals(literal): true
new.intern == literal: true
builder == literal: false
builder == canonical: false
canonical == literal: true
builder.equals(canonical): true
builder after assignment == literal: true
```

**Diễn giải:**

1. Literal `"Java"` được intern tự động, nên biến `literal` trỏ đến đại diện trong pool.
2. `new String("Java")` tạo một đối tượng `String` riêng. Vì vậy `fromNew == literal` là `false`, nhưng `fromNew.equals(literal)` là `true`.
3. `fromNew.intern()` trả đại diện `"Java"` trong pool, do đó có cùng tham chiếu với `literal`.
4. `StringBuilder.toString()` tạo một đối tượng kết quả, nội dung bằng `"Java"` nhưng khác đối tượng literal. `fromBuilder.intern()` tìm thấy đại diện chuẩn và trả về tham chiếu ấy.
5. Sau khi gọi `intern()`, biến `fromBuilder` **vẫn** giữ tham chiếu cũ: `fromBuilder == canonical` là `false`. Chỉ câu lệnh `fromBuilder = fromBuilder.intern();` cuối cùng mới cập nhật biến, khiến `fromBuilder == literal` trở thành `true`.

Ví dụ cố ý dùng literal có sẵn trước khi intern để kết quả tham chiếu **không phụ thuộc** vào việc một chuỗi nội dung chưa gặp lần nào sẽ được thêm vào pool ra sao.

## 4. Literal, hằng biên dịch và nối chuỗi lúc chạy

Không cần gọi `intern()` khi chỉ muốn một string literal: **các string literal của Java được intern**. Theo quy tắc của Java, các **biểu thức hằng kiểu `String`** được tính ở thời điểm biên dịch cũng có cùng đặc tính. Nhưng nối chuỗi dựa trên biến không phải hằng biên dịch là một thao tác lúc chạy; đừng coi kết quả đó là literal.

Lưu **`InternConstantDemo.java`**:

```java
public class InternConstantDemo {
    public static void main(String[] args) {
        String literal = "Java";

        String folded = "Ja" + "va";
        final String constantPart = "Ja";
        String foldedFromFinal = constantPart + "va";

        String mutablePart = "Ja";
        String runtime = mutablePart + "va";

        System.out.println("literal == folded: " + (literal == folded));
        System.out.println("literal == foldedFromFinal: "
                + (literal == foldedFromFinal));
        System.out.println("literal == runtime: "
                + (literal == runtime));
        System.out.println("literal.equals(runtime): "
                + literal.equals(runtime));
        System.out.println("literal == runtime.intern(): "
                + (literal == runtime.intern()));
    }
}
```

```bash
javac InternConstantDemo.java
java InternConstantDemo
```

**Stdout:**

```text
literal == folded: true
literal == foldedFromFinal: true
literal == runtime: false
literal.equals(runtime): true
literal == runtime.intern(): true
```

Vì sao?

- `"Ja" + "va"` là **hằng biên dịch**. Trình biên dịch coi nó là `"Java"`; đại diện literal được intern.
- `constantPart` là **constant variable**: một biến `final` kiểu `String` được khởi tạo bằng biểu thức hằng. `constantPart + "va"` cũng là biểu thức hằng, nên nhận cùng tham chiếu với literal.
- `mutablePart` không phải constant variable. `mutablePart + "va"` được nối lúc chạy, tạo đối tượng kết quả riêng; vì vậy `literal == runtime` là `false`, dù nội dung bằng nhau.
- `runtime.intern()` tìm đại diện literal đã có trong pool. Kết quả `literal == runtime.intern()` là `true`.

**Chú ý:** không phải **mọi biến `final`** đều tạo biểu thức hằng. Ví dụ `final String part = getInput();` không phải hằng biên dịch, vì giá trị chỉ biết lúc chạy. Phân biệt theo **constant expression**, không chỉ nhìn từ khóa `final`.

**Bài học thực hành:** việc `==` đôi khi cho `true` với hai chuỗi bằng nhau là hệ quả của literal/intern. Nó không biến `==` thành phép so nội dung cho các chuỗi bất kỳ.

## 5. Hai chuỗi động cùng nội dung: intern cho cùng tham chiếu dù pool có gì trước đó

Ta có thể kiểm tra thuộc tính chuẩn hóa tham chiếu mà **không cần đoán** pool đã chứa giá trị hay chưa.

**`InternInvariantDemo.java`**

```java
public class InternInvariantDemo {
    public static void main(String[] args) {
        char[] letters = {'q', 'u', 'a', 'r', 't', 'z'};

        String first = new String(letters);
        String second = new String(letters);
        String other = new String(new char[] {'Q', 'u', 'a', 'r', 't', 'z'});

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.intern == second.intern: "
                + (first.intern() == second.intern()));
        System.out.println("first.intern == other.intern: "
                + (first.intern() == other.intern()));
        System.out.println("first unchanged content: " + first);
    }
}
```

```bash
javac InternInvariantDemo.java
java InternInvariantDemo
```

**Stdout:**

```text
first == second: false
first.equals(second): true
first.intern == second.intern: true
first.intern == other.intern: false
first unchanged content: quartz
```

- Hai lời gọi `new String(letters)` tạo hai đối tượng khác nhau.
- Vì nội dung `first` và `second` bằng nhau, **bất kể** pool có `"quartz"` từ trước hay không, `first.intern() == second.intern()` phải là `true`.
- `other` có chữ đầu là `Q` thay vì `q`; `String.equals()` phân biệt hoa/thường, nên đại diện intern cũng khác.
- Lời gọi `intern()` không thay đổi `first`: nội dung vẫn là `"quartz"` và biến chưa được gán lại.

Nếu pool **chưa** có đại diện tương đương, đặc tả của `intern()` cho phép chính đối tượng đầu tiên được thêm vào làm đại diện. Nếu pool **đã** có, nó trả đại diện hiện hữu. Vì không kiểm soát được mọi chuỗi mà JVM/thư viện có thể đã intern trước đó, ví dụ không giả định `first == first.intern()` luôn đúng hoặc luôn sai.

## 6. “Chuẩn hóa tham chiếu” khác với chuẩn hóa văn bản Unicode

`String.intern()` dùng tiêu chí **cùng nội dung theo `String.equals()`**, nên không tự xóa khoảng trắng, đổi chữ hoa thành chữ thường, hay chuẩn hóa Unicode.

Chẳng hạn:

- `"ready"` và `"READY"` không `equals()`, vì khác chữ hoa/thường. Chúng có hai tham chiếu chuẩn khác nhau.
- `"Java"` và `"Java "` không `equals()`, vì một chuỗi có dấu cách ở cuối.
- `"\u00E9"` (é dạng dựng sẵn: một code point) và `"e\u0301"` (e và dấu sắc kết hợp: hai code point) có thể trông giống nhau nhưng **không** `equals()` và **không** trở thành một đối tượng chỉ nhờ `intern()`.

Nếu yêu cầu nghiệp vụ cần so sánh các dạng Unicode tương đương, **chuẩn hóa văn bản trước** bằng `java.text.Normalizer`, rồi mới so sánh hoặc intern nếu thật sự cần chia sẻ tham chiếu.

**`InternUnicodeDemo.java`**

```java
import java.text.Normalizer;

public class InternUnicodeDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw equals: "
                + composed.equals(decomposed));
        System.out.println("raw intern ==: "
                + (composed.intern() == decomposed.intern()));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + composed.equals(normalized));
        System.out.println("NFC intern ==: "
                + (composed.intern() == normalized.intern()));
    }
}
```

```bash
javac InternUnicodeDemo.java
java InternUnicodeDemo
```

**Stdout:**

```text
raw equals: false
raw intern ==: false
NFC equals: true
NFC intern ==: true
```

`Normalizer.Form.NFC` giải quyết dạng Unicode tương đương trong ví dụ. Nó không mặc định giải quyết phân biệt hoa/thường, ngữ nghĩa ngôn ngữ, hay các quy tắc so sánh theo locale. Dùng `intern()` **sau** bước chuẩn hóa chỉ khi việc chia sẻ tham chiếu thật sự có ích; `equals()` trên chuỗi đã chuẩn hóa vẫn đủ để kiểm tra nội dung.

## 7. Khi nào dùng `intern()` và khi nào dùng `equals()`?

| Mục tiêu | Công cụ phù hợp | Lý do |
|---|---|---|
| Kiểm tra hai chuỗi biểu diễn cùng văn bản | `a.equals(b)`, hoặc `Objects.equals(a, b)` khi có thể null | Đúng theo nội dung mà không phụ thuộc pool |
| Đảm bảo hai chuỗi có nội dung bằng nhau dùng cùng tham chiếu chuẩn | `a.intern()`, `b.intern()` | Hai kết quả `intern()` của chuỗi bằng nhau có cùng định danh |
| So sánh hai biến có trỏ đúng cùng một đối tượng hay không | `a == b` | So sánh định danh đối tượng, không tự so nội dung |
| Lấy một literal làm chuỗi hằng | Viết `"text"` | Literal được intern tự động |
| Tìm khóa bằng văn bản trong `HashMap<String, ...>` | Để `HashMap` sử dụng `equals()`/`hashCode()` | Không cần intern để lookup đúng |
| Giảm đối tượng lặp lại của tập giá trị tương đối nhỏ, xuất hiện nhiều lần | Cân nhắc intern nếu đo đạc xác nhận có lợi | Pool cũng tốn bộ nhớ và chi phí xử lý; cần đo trên workload thực |
| Chuẩn hóa chữ Unicode hoặc so không phân biệt hoa/thường | `Normalizer` hoặc quy tắc so sánh văn bản riêng | Intern không thực hiện các phép biến đổi văn bản |

### Ví dụ: HashMap vẫn tra khóa đúng dù tham chiếu khác nhau

**`MapWithoutInternDemo.java`**

```java
import java.util.HashMap;
import java.util.Map;

public class MapWithoutInternDemo {
    public static void main(String[] args) {
        Map<String, Integer> levels = new HashMap<>();
        levels.put("READY", 7);

        String input = new String("READY");

        System.out.println("same reference: " + (input == "READY"));
        System.out.println("same content: " + input.equals("READY"));
        System.out.println("lookup: " + levels.get(input));
        System.out.println("contains: " + levels.containsKey(input));
    }
}
```

```bash
javac MapWithoutInternDemo.java
java MapWithoutInternDemo
```

**Stdout:**

```text
same reference: false
same content: true
lookup: 7
contains: true
```

`HashMap<String, Integer>` dùng `hashCode()` và `equals()` của `String` để nhận diện khóa. Việc `input` là đối tượng riêng **không** ngăn tra cứu. Nếu chỉ cần tra cứu, intern từng khóa hoặc từng đầu vào là không cần thiết và có thể gây thêm chi phí.

### So sánh an toàn khi có thể null

`intern()` và `equals()` đều gọi trên đối tượng. Với `candidate == null`, `candidate.intern()` và `candidate.equals("READY")` đều ném `NullPointerException`. Có thể dùng:

```java
"READY".equals(candidate);          // an toàn nếu candidate null
java.util.Objects.equals(a, b);      // an toàn nếu a/b null
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. `Objects.equals(null, null)` trả `true` vì cả hai tham chiếu cùng null; điều đó không tạo một chuỗi rỗng hay đối tượng intern nào.

## 8. Hợp đồng của intern và các giới hạn thực tế

### 8.1. Tại sao không dùng `==` thay cho `equals()` trong mã nghiệp vụ?

Nếu **cả hai tham chiếu chắc chắn đã intern**, `==` sẽ phản ánh nội dung bằng nhau. Tuy nhiên, trong chương trình thực tế, dữ liệu có thể đến từ file, HTTP, cơ sở dữ liệu, `StringBuilder`, người dùng hoặc thư viện bên ngoài. Không có bảo đảm mọi đầu vào đã intern, trừ khi chính ứng dụng thiết kế và duy trì ràng buộc đó.

Một đoạn mã như:

```java
if (status == "READY") { /* ... */ }
```

là **mã minh họa lỗi khi dùng để so nội dung**: nó có thể vô tình chạy đúng với literal nhưng sai với một `new String("READY")` hay kết quả được tạo lúc chạy. Nếu mục tiêu là so nội dung, viết:

```java
if ("READY".equals(status)) { /* ... */ }
```

Điều này rõ ý định hơn và an toàn khi `status` có thể null.

### 8.2. Intern không thay thế quản lý dữ liệu

Không nên tự động intern **mọi** chuỗi đi vào ứng dụng:

- Mỗi lần intern cần tra cứu/duy trì dữ liệu của pool; gọi dày đặc có chi phí CPU, bộ nhớ và tương tác với quản lý bộ nhớ.
- Nếu nhiều giá trị **duy nhất** hoặc đầu vào không giới hạn số lượng, lợi ích chia sẻ nhỏ trong khi chi phí vẫn phát sinh.
- Nếu nội dung nhỏ, lặp lại rất nhiều, có thể tiết kiệm số đối tượng trùng nhau; song phải đo đạc bằng profiler/benchmark trên dữ liệu đại diện để biết có thực sự có lợi.
- Không dựa vào giả định “mọi chuỗi đã intern sống vĩnh viễn” hoặc “pool không bao giờ tốn bộ nhớ”: chính sách lưu giữ/thu gom và cách triển khai có thể khác theo JVM và phiên bản.
- Không coi intern như một cơ chế quản lý cache nghiệp vụ đầy đủ: không có metadata, giới hạn kích thước hay chính sách loại bỏ riêng theo ứng dụng để tùy chỉnh như một cache thông thường.

Nếu tập nhãn trạng thái nhỏ và được kiểm soát, có thể cân nhắc enum hoặc mã định danh nghiệp vụ thay vì ép mọi giá trị người dùng nhập thành chuỗi intern.

### 8.3. Không dùng chuỗi intern làm khóa đồng bộ tùy tiện

Ví dụ:

```java
synchronized (userId.intern()) {
    // mã minh họa: khóa có thể bị chia sẻ ngoài ý muốn
}
```

Đây là **ví dụ cần tránh**, không phải mẫu đồng bộ khuyến nghị. Mọi thành phần intern nội dung giống `userId` đều có thể nhận cùng đối tượng khóa, kể cả mã khác nằm ngoài vùng kiểm soát. Điều này có thể gây tranh chấp khóa hoặc tương tác không dự kiến giữa các thành phần. Hãy quản lý khóa riêng có vòng đời và phạm vi rõ ràng; không biến string pool chung thành hệ thống khóa nghiệp vụ.

### 8.4. Tham chiếu chuẩn không phải là giá trị được băm

`intern()` không trả về ID số, mã băm hay con trỏ bộ nhớ có thể đem lưu vào file. Nó trả về **tham chiếu `String`**. Không nên dùng `System.identityHashCode()` để thay kiểm tra `==` hoặc để xác nhận tham chiếu chuẩn: giá trị hash định danh không nhất thiết duy nhất cho mọi đối tượng. Khi cần kiểm tra nội dung, `equals()` vẫn là lựa chọn đúng.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật | Cách làm đúng |
|---|---|---|
| Hai chuỗi có cùng nội dung thì `==` luôn `true` | `==` so tham chiếu; hai đối tượng riêng có thể `equals()` nhưng không `==` | Dùng `equals()` cho nội dung |
| Gọi `a.intern();` sẽ khiến biến `a` trỏ sang pool | `intern()` **trả về** tham chiếu chuẩn; không tự gán biến | Khi thật sự cần, dùng `a = a.intern();` |
| Intern tạo đối tượng mới mỗi lần | Nếu đã có đại diện, trả tham chiếu hiện hữu; nếu chưa, có thể thêm chính đối tượng gọi | Hiểu đúng hợp đồng pool |
| Mọi lời gọi `s.intern()` chắc chắn khiến `s == s.intern()` | Tùy `s` đã là đối tượng chuẩn hay chưa | Chỉ dựa vào `s.intern() == t.intern()` với chuỗi bằng nhau |
| `"Ja" + "va"` và nối biến lúc chạy có cùng hành vi tham chiếu | Biểu thức hằng được xử lý lúc biên dịch; nối lúc chạy sinh kết quả riêng | Không suy tính bằng nhau qua `==` |
| Intern sẽ xử lý Unicode, dấu, chữ hoa/thường | Pool chỉ gom những chuỗi `equals()` | Chuẩn hóa nội dung trước nếu nghiệp vụ yêu cầu |
| Muốn `HashMap` tra chuỗi chính xác phải intern | `HashMap` dựa trên `equals()` và `hashCode()` | Dùng khóa `String` bình thường |
| Càng intern nhiều càng tiết kiệm bộ nhớ | Pool và chi phí xử lý có overhead; chuỗi ít lặp lại không chắc có lợi | Đo đạc, chỉ dùng khi có lý do |
| Có thể dùng chuỗi intern làm lock mặc định | Các phần khác của JVM có thể chia sẻ cùng đối tượng chuẩn | Dùng cơ chế khóa thuộc quyền kiểm soát của ứng dụng |

## 10. Tự kiểm tra kiến thức

Đọc chương trình sau và dự đoán kết quả trước khi chạy:

**`InternSelfCheck.java`**

```java
public class InternSelfCheck {
    public static void main(String[] args) {
        String a = "cat";
        String b = new String("cat");
        String c = b.intern();

        System.out.println(a == b);
        System.out.println(a == c);
        System.out.println(b.equals(c));

        b = b.intern();
        System.out.println(a == b);

        String d = new String("CAT");
        System.out.println(a.intern() == d.intern());
    }
}
```

```bash
javac InternSelfCheck.java
java InternSelfCheck
```

**Stdout:**

```text
false
true
true
true
false
```

- `a` là literal đã intern; `b` là một đối tượng mới có cùng nội dung nên ban đầu `a == b` là `false`.
- `c = b.intern()` lấy đại diện literal `"cat"`, vì thế `a == c` là `true`.
- `b.equals(c)` là `true` bởi nội dung giống nhau, không liên quan trực tiếp đến định danh.
- `b = b.intern()` cập nhật biến `b` thành tham chiếu chuẩn nên `a == b` chuyển thành `true`.
- `"CAT"` khác `"cat"` theo `equals()`, do vậy các kết quả intern có tham chiếu khác nhau.

**Ghi nhớ:** `equals()` trả lời câu hỏi **“hai chuỗi có cùng nội dung không?”**; `intern()` trả một **tham chiếu chuẩn** cho nội dung đó; `==` trả lời câu hỏi **“hai tham chiếu có trỏ cùng một đối tượng không?”**. Khi biết chắc hai chuỗi đều đã intern, có thể dùng `==` để kiểm tra tính đồng nhất của chúng; còn trong logic ứng dụng thông thường, `equals()`/`Objects.equals()` diễn đạt đúng yêu cầu so sánh văn bản và tránh phụ thuộc vào chi tiết xuất xứ của chuỗi.
