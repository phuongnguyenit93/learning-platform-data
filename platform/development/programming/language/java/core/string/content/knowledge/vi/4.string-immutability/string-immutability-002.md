# Phân biệt `final` của biến với tính bất biến của đối tượng trong Java

Một nhầm lẫn rất phổ biến khi học Java là cho rằng thêm `final` vào biến sẽ khiến **đối tượng** mà biến tham chiếu đến trở nên bất biến. Trên thực tế, `final` của **biến** và *immutability* của **đối tượng** kiểm soát hai việc khác nhau:

- **`final` của biến**: sau khi biến được gán giá trị hợp lệ, bạn không thể gán lại biến đó. Với biến tham chiếu, điều này cố định **tham chiếu** được lưu trong biến.
- **Đối tượng immutable (bất biến)**: trạng thái quan sát được của chính đối tượng không thay đổi sau khi tạo, bất kể có bao nhiêu biến cùng tham chiếu đến nó.

Hãy ghi nhớ câu ngắn: **`final` giữ ổn định giá trị của biến; immutable giữ ổn định trạng thái của đối tượng.**

## 1. Hai tầng cần phân biệt: biến và đối tượng

Xét lệnh:

```java
final StringBuilder builder = new StringBuilder("Java");
```

Có hai thành phần:

1. **Biến tham chiếu `builder`** chứa một tham chiếu đến đối tượng `StringBuilder`. Từ khóa `final` cấm gán một tham chiếu khác vào biến này.
2. **Đối tượng `StringBuilder`** tồn tại riêng. Nó là loại đối tượng *mutable*: phương thức `append()`, `insert()`, `delete()`… có thể thay đổi nội dung.

Vì vậy:

```java
builder.append(" 17"); // Hợp lệ: đối tượng đang được tham chiếu thay đổi.
// builder = new StringBuilder("Kotlin"); // Lỗi biên dịch: không thể gán lại biến final.
```

Trái lại:

```java
String language = "Java"; // Không khai báo final.
language = language.concat(" 17"); // Hợp lệ: biến trỏ đến kết quả mới.
```

Đối tượng `String` có nội dung `"Java"` vẫn **bất biến**, dù biến `language` không có `final` và có thể được gán lại.

| Trường hợp | Có thể gán lại biến? | Có thể sửa nội dung đối tượng qua API của nó? |
| --- | --- | --- |
| `int x = 1` | Có | Không có đối tượng: `int` là primitive. |
| `final int x = 1` | Không | Không có đối tượng: `int` là primitive. |
| `String s = "A"` | Có | Không, vì `String` bất biến. |
| `final String s = "A"` | Không | Không, vì `String` bất biến. |
| `StringBuilder b = new StringBuilder("A")` | Có | Có, bằng `append()`, `setCharAt()`… |
| `final StringBuilder b = new StringBuilder("A")` | Không | Có, tương tự trường hợp trên. |
| `final int[] a = {1, 2}` | Không thể cho `a` trỏ tới mảng khác | Có, ví dụ `a[0] = 9`. |

Điểm cần chú ý: dấu `=` trong `s = "B"` thay đổi **giá trị biến `s`**; lời gọi `b.append("B")` thay đổi **đối tượng mà `b` đang tham chiếu**. Đó là hai thao tác có bản chất khác nhau.

## 2. `final` trên kiểu nguyên thủy (primitive)

Với `int`, `long`, `double`, `boolean`, `char`… biến giữ trực tiếp giá trị primitive. Khi khai báo `final`, biến không thể nhận giá trị mới:

```java
final int maxRetries = 3;
System.out.println(maxRetries); // 3

// maxRetries = 4; // Lỗi biên dịch.
// maxRetries++;    // Lỗi biên dịch: phép tăng cũng phải gán giá trị mới.
```

Một biến `final` chỉ được **gán một lần theo từng đường chạy hợp lệ**. Nó có thể được khai báo trước rồi gán sau, miễn trình biên dịch chứng minh việc gán diễn ra đúng một lần:

```java
final int port;
boolean isProduction = true;

if (isProduction) {
    port = 443;
} else {
    port = 8080;
}

System.out.println(port); // 443
```

Đây là ví dụ đoạn mã đặt trong phương thức; kết quả phụ thuộc giá trị `isProduction` đã đặt là `true`. Các trường `final` trong lớp cũng có quy tắc khởi tạo riêng: instance field thường được khởi tạo tại nơi khai báo hoặc trong constructor của mọi đường khởi tạo; `static final` được khởi tạo theo quy tắc trường tĩnh. Không nên diễn đạt `final` là “luôn là compile-time constant”: chỉ một số biểu thức primitive/`String` `final` thỏa điều kiện *constant variable* của Java Language Specification.

## 3. `final` trên biến tham chiếu: không đổi đích trỏ, vẫn có thể đổi trạng thái

Tham chiếu `final` không thể trỏ sang đối tượng mới, nhưng đối tượng hiện tại vẫn có thể sửa được nếu loại của nó cho phép.

### Mảng

```java
final int[] scores = {10, 20};
scores[0] = 99;            // Hợp lệ.
System.out.println(scores[0]); // 99

// scores = new int[] {1, 2}; // Lỗi biên dịch: gán lại biến scores.
```

Bản thân **mảng Java là mutable**: `final` trên biến không đóng băng các phần tử.

### Collection và đối tượng tùy biến

```java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");           // Hợp lệ: sửa trạng thái ArrayList.
names.add("Binh");
System.out.println(names); // [An, Binh]

// names = new java.util.ArrayList<>(); // Lỗi biên dịch.
```

Nếu hai biến cùng trỏ đến một đối tượng mutable, việc sửa qua biến này sẽ được quan sát qua biến kia:

```java
final StringBuilder original = new StringBuilder("A");
StringBuilder alias = original;

alias.append("B");
System.out.println(original); // AB
```

`final` **không loại bỏ aliasing** (nhiều tham chiếu tới cùng một đối tượng) và không ngăn thay đổi trạng thái thông qua alias.

## 4. Đối tượng immutable: có thể đổi tham chiếu, không thể sửa giá trị cũ

`String` là ví dụ điển hình của một lớp có hợp đồng bất biến. Không có thao tác công khai kiểu `append()` hoặc `setCharAt()` thay đổi trực tiếp nội dung của một instance `String`. Các lời gọi như `concat()`, `replace()` hoặc `toUpperCase()` trả về kết quả mới về **giá trị**; chuỗi ban đầu vẫn giữ nguyên. Cài đặt có thể trả về chính instance cũ khi kết quả không thay đổi, nên “immutable” không đồng nghĩa “mọi thao tác đều cấp phát instance mới”.

```java
String title = "Java";
String oldTitle = title;

title = title + " 17";

System.out.println(title);    // Java 17
System.out.println(oldTitle); // Java
```

Ở đây, `title` được gán sang kết quả `"Java 17"`, còn `oldTitle` vẫn tham chiếu tới đối tượng `"Java"`. Không có thao tác nào “sửa chuỗi Java thành Java 17”.

Nếu thêm `final` vào `title`:

```java
final String title = "Java";
String another = title.concat(" 17"); // Hợp lệ, title vẫn là "Java".
// title = another; // Lỗi biên dịch vì title là final.
```

Tính bất biến vẫn như cũ; điểm mới duy nhất là không thể gán lại biến `title`.

## 5. Ví dụ Java 17+ chạy độc lập: đối chiếu cả bốn tình huống

Lưu mã sau vào tệp `FinalVsImmutableDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalVsImmutableDemo {
    public static void main(String[] args) {
        // (1) final + primitive: không thể gán lại biến.
        final int limit = 3;
        System.out.println("limit = " + limit);

        // (2) final + mutable object: không gán lại được tham chiếu,
        // nhưng nội dung đối tượng vẫn thay đổi được.
        final StringBuilder buffer = new StringBuilder("Ja");
        buffer.append("va");
        System.out.println("buffer = " + buffer);

        final int[] scores = {1, 2};
        scores[0] = 9;
        System.out.println("scores[0] = " + scores[0]);

        final List<String> names = new ArrayList<>(List.of("An"));
        names.add("Binh");
        System.out.println("names = " + names);

        // (3) Tham chiếu KHÔNG final + immutable String:
        // biến đổi đích trỏ, đối tượng chuỗi cũ không đổi.
        String first = "Java";
        String oldFirst = first;
        first = first.concat(" 17");
        System.out.println("first = " + first);
        System.out.println("oldFirst = " + oldFirst);

        // (4) final + immutable String: cả hai bảo đảm cùng tồn tại.
        final String greeting = "Hi";
        String newGreeting = greeting.concat("!");
        System.out.println("greeting = " + greeting);
        System.out.println("newGreeting = " + newGreeting);
    }
}
```

Biên dịch và chạy:

```bash
javac FinalVsImmutableDemo.java
java FinalVsImmutableDemo
```

Kết quả chính xác:

```text
limit = 3
buffer = Java
scores[0] = 9
names = [An, Binh]
first = Java 17
oldFirst = Java
greeting = Hi
newGreeting = Hi!
```

**Diễn giải:** những dòng cập nhật `StringBuilder`, mảng và `ArrayList` thay đổi nội dung đối tượng dù biến là `final`; phép nối `String` không thay đổi instance cũ dù biến `first` có thể được gán lại. Nếu bỏ dấu chú thích ở các phép gán lại biến `final` trong các ví dụ trước, lỗi xảy ra **lúc biên dịch**, không phải lúc chạy.

## 6. `final` ở những vị trí khác không có cùng ý nghĩa với immutable

### Tham số `final`

```java
static void addTag(final StringBuilder target) {
    target.append("-ok"); // Hợp lệ: sửa đối tượng.
    // target = new StringBuilder(); // Lỗi biên dịch: gán lại tham số.
}
```

`final` cấm thay đổi **biến tham số bên trong phương thức**. Java vẫn truyền **giá trị của tham chiếu** vào tham số; caller và callee có thể trỏ tới cùng đối tượng mutable. `final` không biến lời gọi thành deep copy hay chặn cập nhật đối tượng.

### Trường `final` trong lớp

```java
class MessageBuffer {
    private final StringBuilder content = new StringBuilder();

    void write(String text) {
        content.append(text); // Hợp lệ.
    }

    String read() {
        return content.toString();
    }
}
```

Trường `content` không được gán lại sau khởi tạo, nhưng trạng thái đối tượng `StringBuilder` vẫn thay đổi. Vì thế **“mọi field đều `final`” không chứng minh cả lớp là immutable**.

### `final class`

```java
final class MutableCounter {
    private int value;

    void increment() {
        value++; // Vẫn sửa được state.
    }

    int get() {
        return value;
    }
}
```

`final class` cấm kế thừa, không cấm thay đổi trạng thái. Một thiết kế bất biến thường dùng `final class` để tránh lớp con phá vỡ hợp đồng, nhưng chỉ riêng từ khóa này chưa đủ để tạo tính bất biến. Tương tự, `final` trên **phương thức** cấm override phương thức đó chứ không làm phương thức thành read-only.

### Biến *effectively final*

Biến local không viết `final` nhưng được gán một lần và không bị gán lại có thể được trình biên dịch coi là *effectively final*, cho phép lambda/lớp nội bộ truy cập:

```java
String prefix = "Hello, ";
Runnable task = () -> System.out.println(prefix + "Java");
task.run(); // Hello, Java

// prefix = "Hi, "; // Nếu thêm lệnh gán lại này,
//                   // lambda ở trên không còn hợp lệ để biên dịch.
```

*Effectively final* là quy tắc về **giá trị của biến được capture**, không phải tính bất biến của đối tượng mà biến tham chiếu.

## 7. Cần gì để tạo một đối tượng thực sự bất biến?

Một lớp tự viết chỉ nên được gọi là immutable khi **trạng thái quan sát được sau khởi tạo không thể bị thay đổi** thông qua các đường truy cập mà lớp cung cấp, kể cả khi đối tượng được chia sẻ. Các nguyên tắc phổ biến:

1. Khởi tạo đầy đủ giá trị trong constructor hoặc phương thức tạo; không mở setter làm thay đổi trạng thái.
2. Dùng `private final` cho các trường trạng thái khi thích hợp: chặn thay thế giá trị trường sau khởi tạo, nhưng phải kiểm tra sâu hơn nếu trường trỏ tới object mutable.
3. Không làm rò rỉ tham chiếu tới bộ dữ liệu mutable nội bộ. **Sao chép phòng vệ** (*defensive copy*) khi nhận dữ liệu mutable và khi trả dữ liệu mutable.
4. Nếu trường chứa collection, xem xét tính mutable của **bản thân collection lẫn từng phần tử**; sao chép một danh sách không tự làm từng phần tử bất biến.
5. Ngăn lớp con làm suy yếu hợp đồng bất biến, chẳng hạn dùng `final class` hoặc một thiết kế kế thừa có kiểm soát; không để `this` thoát ra khi chưa khởi tạo xong.

Ví dụ thiết kế snapshot bất biến với các phần tử `String` (vốn bất biến). Tạo tệp `ImmutableRosterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableRosterDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> source) {
            this.members = List.copyOf(source);
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An"));
        Roster roster = new Roster(input);

        input.add("Binh"); // Sửa nguồn sau khi tạo roster.
        System.out.println("input = " + input);
        System.out.println("roster = " + roster.members());

        try {
            roster.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("roster members cannot be modified");
        }

        System.out.println("roster after attempt = " + roster.members());
    }
}
```

Lệnh chạy:

```bash
javac ImmutableRosterDemo.java
java ImmutableRosterDemo
```

Kết quả:

```text
input = [An, Binh]
roster = [An]
roster members cannot be modified
roster after attempt = [An]
```

Tại sao `Roster` đạt tính bất biến trong ví dụ này?

- Trường `members` là `private final`: không thể gán lại một list khác sau khởi tạo.
- `List.copyOf(source)` tạo một danh sách không hỗ trợ chỉnh sửa cấu trúc, độc lập với thay đổi sau đó của `ArrayList` nguồn trong ví dụ. Nó không cho thêm, xóa hoặc thay thế phần tử thông qua API của list.
- Từng phần tử là `String` vốn bất biến, nên ở đây không có object mutable bên trong có thể bị thay đổi thông qua alias.
- Lớp `Roster` là `final` và không cung cấp setter hoặc đường truy cập nội bộ có thể ghi.

**Giới hạn quan trọng:** `List.copyOf` là sao chép **nông** (*shallow*) theo phần tử; nó không sao chép sâu các đối tượng đang nằm trong list. Ví dụ nếu sử dụng `List<StringBuilder>`, một bên giữ `StringBuilder` cũ vẫn có thể `append()` để thay đổi nội dung phần tử mà danh sách bản sao tham chiếu. Muốn bất biến sâu phải dùng các phần tử bất biến hoặc tạo bản sao phù hợp của những phần tử mutable. `List.copyOf` cũng không chấp nhận phần tử `null`.

### Phân biệt bản sao và view không cho sửa

Hai khái niệm dễ bị nhầm:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

Đoạn mã trên là **fragment** cần đặt trong phương thức, với các import `java.util.ArrayList`, `java.util.Collections` và `java.util.List`. `Collections.unmodifiableList(source)` tạo *view* không cho sửa **thông qua view**, nhưng nguồn `source` vẫn có thể sửa và view sẽ phản ánh thay đổi. Ngược lại, `List.copyOf(source)` cho danh sách snapshot không bị ảnh hưởng bởi các thay đổi cấu trúc về sau của `source` trong ví dụ trên.

Khi cần bảo vệ một mảng, có thể áp dụng cả hai hướng sao chép:

```java
final class SafeBytes {
    private final byte[] data;

    SafeBytes(byte[] input) {
        this.data = input.clone(); // Không giữ mảng mutable của caller.
    }

    byte[] copyData() {
        return data.clone();       // Không lộ mảng nội bộ để caller sửa.
    }
}
```

Nếu chỉ dùng `private final byte[] data = input;` mà giữ trực tiếp mảng ngoài, caller vẫn có thể sửa `input[0]` và làm thay đổi trạng thái đang được quan sát của `SafeBytes`.

## 8. Tác động đến chia sẻ và đa luồng

- **Biến tham chiếu `final` không khiến đối tượng tự an toàn đa luồng.** Chẳng hạn, hai luồng cùng gọi `append()` trên cùng một `StringBuilder` vẫn có vấn đề truy cập đồng thời; `final StringBuilder shared` không giải quyết race condition đó.
- **Đối tượng immutable có thể được nhiều luồng đọc chung một cách thuận tiện.** Ví dụ, sau khi tham chiếu được công bố đúng cách giữa các luồng, nhiều luồng có thể dùng một đối tượng `String` hoặc `Roster` bất biến mà không cần khóa chỉ để ngăn việc sửa *nội dung*.
- **Gán lại một biến chứa tham chiếu đến các đối tượng immutable vẫn là thay đổi trạng thái của nơi chứa biến.** Nếu nhiều luồng thay đổi một trường `String status`, còn cần xem xét cơ chế công bố và đồng bộ (`volatile`, `synchronized`, atomic reference…) tùy thao tác.
- Các trường `final` có một số đảm bảo về mô hình bộ nhớ Java khi đối tượng được xây dựng đúng, nhưng **không** có nghĩa mọi object reachable từ trường `final` cũng bất biến hoặc mọi thao tác sử dụng chúng đều an toàn đa luồng.

## 9. Những ngộ nhận cần tránh

| Nhận định | Kết luận |
| --- | --- |
| “Đối tượng gắn với biến `final` không thể sửa.” | **Sai.** `final` chỉ cấm gán lại biến; `ArrayList`, mảng, `StringBuilder` vẫn mutable. |
| “Biến không `final` thì đối tượng chắc chắn mutable.” | **Sai.** `String s = "A"` không `final`, nhưng đối tượng `String` vẫn immutable. |
| “Mọi field là `final` nên toàn bộ class immutable.” | **Sai.** Phần tử mảng, collection, và object mutable được tham chiếu vẫn có thể đổi. |
| “`final class` tức là immutable class.” | **Sai.** Nó chỉ cấm tạo subclass; lớp final vẫn có thể cung cấp setter. |
| “`static final List` là danh sách không thay đổi được.” | **Sai.** `static` và `final` ràng buộc trường, không chặn `add/remove` trên list mutable. |
| “`record` luôn bất biến sâu.” | **Sai.** Component của record không thể gán lại, nhưng component có kiểu mảng/list mutable vẫn có thể chứa trạng thái thay đổi; cần thiết kế sao chép phòng vệ. |
| “`Collections.unmodifiableList` tạo snapshot bất biến.” | **Sai.** Đây là view; sửa backing list sẽ xuất hiện trong view. |
| “Đối tượng immutable đồng nghĩa biến trỏ tới nó không bao giờ đổi.” | **Sai.** Một biến không `final` có thể được gán sang đối tượng immutable khác. |

## 10. Tự kiểm tra

**Câu 1.** Đoạn nào trong mã sau gây lỗi biên dịch?

```java
final StringBuilder b = new StringBuilder("X");
b.append("Y");
// b = new StringBuilder("Z");
```

Trả lời: dòng gán lại `b` (đang được chú thích) gây lỗi biên dịch nếu bỏ chú thích; `append("Y")` hợp lệ và đối tượng trở thành `"XY"`.

**Câu 2.** `name` không được khai báo `final` thì chuỗi có còn bất biến không?

```java
String name = "An";
String remembered = name;
name = "Binh";
System.out.println(remembered);
```

Kết quả là `An`. Hai đối tượng `String` giữ nguyên giá trị; chỉ biến `name` nhận tham chiếu mới.

**Câu 3.** Có cần `final` trên biến để dùng `String` làm khóa `HashMap` không?

Không. Tính bất biến của **chính đối tượng `String`** đã giữ ổn định nội dung dùng cho `equals()` và `hashCode()`; biến chứa tham chiếu khóa không nhất thiết là `final`. `final` có thể giúp chương trình dễ đọc hơn khi muốn đảm bảo biến không bị gán lại, nhưng đó là bảo đảm bổ sung ở cấp biến.

**Điểm cốt lõi:** khi đọc code, hãy luôn hỏi hai câu riêng: **(1) Biến này có được gán lại không? (2) Đối tượng mà nó trỏ tới có thể thay đổi trạng thái không?** Chỉ từ `final` trên biến, bạn trả lời được câu thứ nhất; để trả lời câu thứ hai, phải xem hợp đồng và thiết kế của loại đối tượng.

## Tài liệu tham khảo

- [Java Language Specification §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4) — ràng buộc phép gán và khái niệm effectively final.
- [Java SE 21 API — `String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html) — tính bất biến và API thao tác chuỗi.
- [Java SE 21 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — snapshot không thể sửa cấu trúc và tính chất shallow của phần tử.
- [Java SE 21 API — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) — view không cho sửa và liên hệ với backing list.
