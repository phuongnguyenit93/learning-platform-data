# StringBuilder: `equals`, `compareTo` và giới hạn chia sẻ giữa nhiều luồng

`StringBuilder` là lớp **chuỗi có thể thay đổi (mutable)** trong Java. Nó phù hợp để tạo hoặc chỉnh sửa văn bản qua các thao tác `append`, `insert`, `replace`, `delete` mà không cần tạo một giá trị `String` mới cho từng lần nối. Nhưng tính mutable kéo theo ba vấn đề cần phân biệt: **so sánh đối tượng bằng `equals`**, **so sánh nội dung có thứ tự bằng `compareTo`**, và **an toàn khi nhiều luồng cùng truy cập**.

Điểm quan trọng nhất:

- `StringBuilder` **không ghi đè `Object.equals(Object)`**. Hai builder riêng biệt, dù chứa cùng nội dung, vẫn không bằng nhau theo `equals`.
- Trên Java 11 trở lên, `StringBuilder` có `compareTo(StringBuilder)` để **so sánh nội dung theo thứ tự từ điển**. Hai builder khác đối tượng nhưng cùng nội dung trả kết quả `0`.
- `StringBuilder` **không cung cấp đồng bộ hóa cho truy cập đồng thời**. Nếu chia sẻ một builder có thể bị thay đổi cho nhiều luồng, chương trình phải tự tổ chức đồng bộ và quy tắc sở hữu rõ ràng.

Đây không phải mâu thuẫn của Java: `equals` và `compareTo` thực hiện **hai hợp đồng khác nhau**, còn an toàn luồng phụ thuộc việc đọc/ghi được phối hợp ra sao.

## 1. `StringBuilder` khác `String` như thế nào?

| Tiêu chí | `String` | `StringBuilder` |
| --- | --- | --- |
| Dữ liệu văn bản | Bất biến sau khi tạo | Có thể thêm, xóa, thay thế ký tự |
| Dùng cho | Giá trị văn bản, khóa so sánh, tham số API | Xây dựng/chỉnh sửa văn bản tại một nơi |
| `equals(Object)` | So sánh nội dung hai `String` | Kế thừa `Object.equals`: so sánh cùng tham chiếu |
| `compareTo(...)` | So sánh từ điển hai `String` | So sánh từ điển hai `StringBuilder` trên Java 11+ |
| `hashCode()` | Dựa trên nội dung | Kế thừa `Object.hashCode`: không phải mã băm dựa trên nội dung |
| Khả năng chia sẻ giữa luồng | Giá trị bất biến thuận tiện để chia sẻ sau khi công bố an toàn | Cần bảo vệ khi các luồng có thể cùng đọc/ghi |

Ví dụ, `StringBuilder sb = new StringBuilder("Java");` tạo builder có nội dung ban đầu là `Java`; `sb.append(" Core")` làm thay đổi chính builder thành `Java Core`. Đây là hành vi khác với `String`: gọi `text.concat(" Core")` không sửa `text`, mà tạo một giá trị chuỗi tương ứng để bên gọi sử dụng.

`StringBuilder` **không phải** một `String`: dù cả hai chứa văn bản, không thể truyền builder trực tiếp vào mọi API yêu cầu `String`. Khi cần giá trị `String` để so sánh nội dung hoặc truyền đi, dùng `sb.toString()`.

## 2. `equals(Object)` của `StringBuilder` là so sánh danh tính

Khác với `String`, lớp `StringBuilder` **không override `equals(Object)`**. Nó thừa hưởng hành vi từ `Object`: phương thức chỉ trả về `true` khi đối tượng được so sánh là **chính cùng một đối tượng**.

```java
StringBuilder first = new StringBuilder("Java");
StringBuilder second = new StringBuilder("Java");
StringBuilder alias = first;

System.out.println(first == second);       // false
System.out.println(first.equals(second));  // false
System.out.println(first == alias);        // true
System.out.println(first.equals(alias));   // true
```

Đoạn trên là mã minh họa đặt bên trong một phương thức Java. Hai builder `first` và `second` được tạo độc lập nên khác tham chiếu; `alias` chỉ là một tham chiếu khác trỏ tới đối tượng của `first`.

Nếu muốn kiểm tra **nội dung** hai builder, đừng gọi `first.equals(second)` rồi kỳ vọng nó hoạt động như `String.equals`. Có thể tạo hai giá trị `String` bất biến:

```java
boolean sameText = first.toString().equals(second.toString());
```

Kết quả là `true` nếu nội dung bằng nhau tại thời điểm chụp mỗi giá trị. Nếu đang có nhiều luồng thay đổi builder, cần đồng bộ hóa để có được snapshot phù hợp; bản thân `toString()` không làm mọi thao tác trên builder trở nên thread-safe.

### Thử nghiệm hoàn chỉnh

Tệp `BuilderEqualityDemo.java`:

```java
public class BuilderEqualityDemo {
    public static void main(String[] args) {
        StringBuilder a = new StringBuilder("abc");
        StringBuilder b = new StringBuilder("abc");
        StringBuilder same = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(same): " + a.equals(same));
        System.out.println("strings equal: " +
                a.toString().equals(b.toString()));
        System.out.println("builder equals String: " +
                a.equals("abc"));

        a.append('!');
        System.out.println("after append: " + a);
        System.out.println("alias sees change: " + same);
        System.out.println("now strings equal: " +
                a.toString().equals(b.toString()));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 BuilderEqualityDemo.java
java BuilderEqualityDemo
```

Đầu ra:

```text
a == b: false
a.equals(b): false
a.equals(same): true
strings equal: true
builder equals String: false
after append: abc!
alias sees change: abc!
now strings equal: false
```

`a.equals("abc")` cũng trả `false` vì đối số là một `String`, không phải cùng đối tượng `a`. `alias` cùng trỏ đến `a` nên nhìn thấy thay đổi khi `a.append('!')` được gọi.

## 3. `compareTo(StringBuilder)`: so sánh nội dung theo thứ tự từ điển

Từ **Java 11**, `StringBuilder` triển khai `Comparable<StringBuilder>` và cung cấp phương thức:

```java
public int compareTo(StringBuilder another)
```

Phương thức dùng **thứ tự từ điển (lexicographic order)** của các đơn vị ký tự UTF-16 trong nội dung builder:

- Trả về **số âm** nếu nội dung builder bên trái đứng trước nội dung bên phải.
- Trả về **`0`** nếu hai dãy UTF-16 code unit có cùng nội dung.
- Trả về **số dương** nếu nội dung bên trái đứng sau nội dung bên phải.

Không nên đặt điều kiện `compareTo(...) == -1` hoặc `== 1` để nhận biết lớn/nhỏ. Hợp đồng cần dùng là **dấu của kết quả** (`< 0`, `== 0`, `> 0`), không phải một độ lớn cụ thể.

Ví dụ:

```java
StringBuilder a = new StringBuilder("apple");
StringBuilder b = new StringBuilder("banana");
StringBuilder c = new StringBuilder("apple");

System.out.println(a.compareTo(b) < 0); // true
System.out.println(b.compareTo(a) > 0); // true
System.out.println(a.compareTo(c) == 0); // true
System.out.println(a.equals(c));         // false
```

`a.compareTo(c) == 0` có nghĩa **nội dung đang bằng nhau**, không có nghĩa `a` và `c` là cùng đối tượng. Chính vì vậy, Java API cảnh báo **thứ tự tự nhiên này không nhất quán với `equals`** (`natural ordering inconsistent with equals`).

### Chương trình minh họa có kết quả kiểm chứng được

Tệp `BuilderComparisonDemo.java`:

```java
public class BuilderComparisonDemo {
    public static void main(String[] args) {
        StringBuilder left = new StringBuilder("apple");
        StringBuilder right = new StringBuilder("banana");
        StringBuilder sameText = new StringBuilder("apple");

        System.out.println("left < right: " +
                (left.compareTo(right) < 0));
        System.out.println("right > left: " +
                (right.compareTo(left) > 0));
        System.out.println("left.compareTo(sameText): " +
                left.compareTo(sameText));
        System.out.println("left.equals(sameText): " +
                left.equals(sameText));

        right.setLength(0);
        right.append("apple");
        System.out.println("after change comparison: " +
                left.compareTo(right));
        System.out.println("after change equals: " +
                left.equals(right));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderComparisonDemo.java
java BuilderComparisonDemo
```

Kết quả:

```text
left < right: true
right > left: true
left.compareTo(sameText): 0
left.equals(sameText): false
after change comparison: 0
after change equals: false
```

Lời gọi `right.setLength(0)` xóa nội dung hiệu dụng của builder, rồi `append("apple")` ghi lại văn bản `apple`. Nội dung thay đổi khiến `compareTo` trả về giá trị mới, trong khi `equals` vẫn là so sánh danh tính và không đổi kết quả vì hai đối tượng vẫn khác nhau.

Không có phép so sánh nội dung “đóng băng” mặc định đối với builder mutable: sau mỗi thay đổi, thứ tự của nó so với builder khác **có thể** đổi.

## 4. `compareTo` không thay thế `equals` và không so sánh được trực tiếp với `String`

Đây là hai thao tác khác nhau:

```java
StringBuilder builder = new StringBuilder("hello");
StringBuilder otherBuilder = new StringBuilder("hello");
String stringValue = "hello";

// Theo danh tính đối tượng:
boolean sameBuilderObject = builder.equals(otherBuilder); // false

// Theo thứ tự nội dung hai builder:
boolean sameBuilderContent = builder.compareTo(otherBuilder) == 0; // true

// Theo nội dung dạng String:
boolean sameAsString = builder.toString().equals(stringValue); // true
```

Đây là mã minh họa nằm trong một phương thức. `compareTo` nhận `StringBuilder`, **không nhận `String`**. Vì vậy `builder.compareTo(stringValue)` không hợp lệ về kiểu; bạn cần quyết định so sánh hai builder bằng `compareTo`, hoặc tạo `String` và dùng `equals`/`compareTo` của `String`.

Để tìm một chuỗi con, hãy dùng các API văn bản thích hợp như `indexOf` (nếu áp dụng cho builder) hoặc snapshot `toString()`, thay vì lấy `compareTo` để suy ra có chứa một từ. `compareTo` chỉ trả về **quan hệ thứ tự giữa toàn bộ nội dung hai đối tượng**.

`StringBuilder.compareTo` cũng không phải bộ so sánh ngôn ngữ tự nhiên: nó dựa trên thứ tự UTF-16 của dữ liệu ký tự và phân biệt hoa/thường. Nếu cần sắp xếp tên người theo quy tắc ngôn ngữ, phải xác định locale và bộ so sánh văn bản phù hợp, thường làm việc với các giá trị `String` bất biến.

## 5. Vì sao `HashSet` và `TreeSet` xử lý builder có cùng nội dung khác nhau?

Điểm không nhất quán giữa `equals` và `compareTo` có hệ quả khi dùng tập hợp:

- `HashSet` xác định trùng nhau bằng `hashCode` và `equals`. `StringBuilder` không override hai phương thức này để dựa trên nội dung, nên **hai builder khác đối tượng** là hai phần tử khác nhau.
- `TreeSet` với thứ tự tự nhiên xác định các phần tử tương đương theo **`compareTo(...) == 0`**. Hai builder có cùng nội dung có thể được xem là một phần tử trong tập dù `equals` của chúng là `false`.

Tệp `BuilderSetDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BuilderSetDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("x");
        StringBuilder second = new StringBuilder("x");

        Set<StringBuilder> hash = new HashSet<>();
        hash.add(first);
        hash.add(second);

        Set<StringBuilder> sorted = new TreeSet<>();
        sorted.add(first);
        sorted.add(second);

        System.out.println("equals: " + first.equals(second));
        System.out.println("compareTo zero: " +
                (first.compareTo(second) == 0));
        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + sorted.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BuilderSetDemo.java
java BuilderSetDemo
```

Kết quả:

```text
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
```

Sự khác biệt **không phải lỗi ngẫu nhiên** của tập hợp; nó xuất phát từ hợp đồng so sánh của `StringBuilder`. `SortedSet` và `SortedMap` dựa vào thứ tự để xác định tương đương, nên việc dùng loại dữ liệu có thứ tự tự nhiên không nhất quán với `equals` có thể gây hành vi ngược kỳ vọng của lập trình viên.

**Không nên dùng builder mutable làm khóa để sắp xếp hoặc định danh theo nội dung.** Nếu cần tập hợp các chuỗi duy nhất theo nội dung, lựa chọn tự nhiên là chuyển sang `String`:

```java
Set<String> texts = new HashSet<>();
texts.add(first.toString());
texts.add(second.toString()); // Cùng nội dung, HashSet giữ một giá trị

System.out.println(texts.size()); // 1
```

Đoạn ví dụ nằm trong phương thức có import `java.util.Set` và `java.util.HashSet`. `String` có `equals`/`hashCode` theo nội dung và bất biến, nên thích hợp hơn khi làm khóa tập hợp/map cho văn bản.

## 6. Mutable builder không phải khóa sắp xếp ổn định

Giả sử `TreeSet<StringBuilder>` đã sắp xếp nội dung builder lúc thêm vào tập. Sau đó một builder bị sửa từ `"a"` thành `"z"`. Cây tìm kiếm **không tự sắp xếp lại** vì nội dung phần tử thay đổi tại chỗ. Những thao tác `contains`, `remove` hoặc duyệt theo thứ tự sau đó có thể không còn phản ánh quan hệ thứ tự mà cấu trúc dữ liệu giả định.

Đây là lý do không nên thêm builder rồi tiếp tục `append` hoặc `delete` trên cùng đối tượng làm khóa:

```java
// Minh họa THIẾT KẾ CẦN TRÁNH:
TreeSet<StringBuilder> values = new TreeSet<>();
StringBuilder key = new StringBuilder("abc");
values.add(key);
key.append("xyz"); // Thay đổi khóa sau khi đã chèn vào TreeSet
```

Đoạn trên cần import `java.util.TreeSet` và nằm trong phương thức; không nên suy ra một kết quả cụ thể cố định cho mọi lần tìm kiếm sau khi khóa bị sửa. Vấn đề là **bất biến sắp xếp của cấu trúc có thể bị phá vỡ**.

Cách an toàn hơn là dùng bản chụp bất biến `String` ngay khi thêm vào tập:

```java
TreeSet<String> values = new TreeSet<>();
StringBuilder input = new StringBuilder("abc");

values.add(input.toString());
input.append("xyz");

System.out.println(values.contains("abc"));    // true
System.out.println(values.contains("abcxyz")); // false
```

Vì tập lưu chuỗi đã chụp tại thời điểm `add`, việc sửa `input` về sau không làm đổi khóa bên trong `TreeSet`.

## 7. `StringBuilder` không đồng bộ hóa cho nhiều luồng

Theo tài liệu Java, `StringBuilder` được thiết kế để dùng khi thao tác xây dựng chuỗi **không cần đồng bộ hóa**. Nó phù hợp với code ở **một luồng** hoặc một builder chỉ thuộc sở hữu riêng của một đơn vị xử lý, giúp giảm chi phí đồng bộ so với `StringBuffer` trong các tình huống tương ứng.

Nhưng `StringBuilder` là mutable. Nếu **cùng một đối tượng** bị nhiều luồng gọi `append`/`delete`/`insert`/`setCharAt` hoặc một luồng đang ghi trong khi luồng khác đọc nội dung mà không có quan hệ đồng bộ phù hợp, có thể xảy ra **data race**:

- Cập nhật từ luồng này có thể không được luồng khác quan sát như mong đợi.
- Các thao tác xen kẽ có thể gây **mất dữ liệu, sai thứ tự hoặc trạng thái trung gian không mong muốn**.
- Đọc `length()`, `charAt()`, `toString()` hoặc `compareTo()` trong lúc luồng khác sửa builder không tự bảo đảm một snapshot nhất quán.
- Không có bảo đảm kết quả cụ thể hoặc một ngoại lệ cố định: một chương trình sai đồng bộ có thể *có vẻ chạy đúng* ở nhiều lần thử nhưng vẫn không an toàn.

**Không phải cứ có hai luồng trong chương trình là mọi builder đều nguy hiểm.** Vấn đề xuất hiện khi các luồng **cùng truy cập đối tượng mutable với ít nhất một thao tác ghi** mà không có phối hợp theo Java Memory Model. Nếu mỗi luồng sở hữu builder riêng, không có việc chia sẻ mutable builder nên không phát sinh rủi ro đó.

### Không nên coi `append` là phép toán nguyên tử khi dùng chung

Đoạn sau không phù hợp để dựa vào trong chương trình nhiều luồng:

```java
// Mã minh họa hành vi cần TRÁNH: shared dùng chung giữa các luồng.
StringBuilder shared = new StringBuilder();

Runnable action = () -> {
    for (int i = 0; i < 1000; i++) {
        shared.append('X');
    }
};
```

Đây là fragment minh họa, không phải chương trình đầy đủ. Nếu tạo hai luồng thực thi `action` đồng thời **không khóa**, không có bảo đảm rằng kết quả luôn có đúng 2000 ký tự. Không nên kèm một “stdout mẫu” cố định cho chương trình có data race, vì đầu ra phụ thuộc thực thi và có thể khác từng lần.

## 8. Ví dụ an toàn: khóa chung bảo vệ mọi thao tác với builder

Một cách phối hợp hợp lệ là bảo vệ mọi lần **đọc và ghi** trên cùng builder bằng **cùng một đối tượng khóa** qua `synchronized`. Khi cần lấy kết quả để xử lý ngoài vùng khóa, tạo một giá trị `String` bất biến trong vùng được bảo vệ.

Tệp `SynchronizedBuilderDemo.java`:

```java
public class SynchronizedBuilderDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuilder shared = new StringBuilder();
        Object lock = new Object();

        Runnable addA = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    shared.append('A');
                }
            }
        };

        Runnable addB = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    shared.append('B');
                }
            }
        };

        Thread first = new Thread(addA);
        Thread second = new Thread(addB);

        first.start();
        second.start();
        first.join();
        second.join();

        String snapshot;
        synchronized (lock) {
            snapshot = shared.toString();
        }

        long countA = snapshot.chars().filter(c -> c == 'A').count();
        long countB = snapshot.chars().filter(c -> c == 'B').count();

        System.out.println("length=" + snapshot.length());
        System.out.println("countA=" + countA);
        System.out.println("countB=" + countB);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SynchronizedBuilderDemo.java
java SynchronizedBuilderDemo
```

Kết quả:

```text
length=2000
countA=1000
countB=1000
```

Thứ tự các ký tự `A`/`B` **không được cố định** vì hai luồng có thể lấy khóa theo những thứ tự khác nhau. Nhưng mọi `append` được bảo vệ bằng cùng khóa, hai luồng đều hoàn thành trước lúc tạo snapshot, nên **tổng số và số lượng từng loại** là xác định như đầu ra trên.

`synchronized(lock)` là một cơ chế phối hợp đơn giản. Quan trọng là **tất cả những nơi cùng truy cập mutable builder phải tuân thủ cùng quy ước đồng bộ**, kể cả đọc. Chỉ khóa một số thao tác ghi mà để các đoạn code khác đọc/ghi tự do sẽ không tạo ra bảo đảm đầy đủ.

## 9. Nếu chỉ cần gửi kết quả sang luồng khác, nên chụp `String` bất biến

Phần lớn ứng dụng không cần chia sẻ một builder mutable cho các luồng khác cùng chỉnh sửa. Một mô hình dễ quản lý hơn:

1. Tạo `StringBuilder` như biến cục bộ trong một phương thức/luồng.
2. Dùng nó để lắp ráp văn bản.
3. Gọi `toString()` để thu được giá trị bất biến.
4. Chuyển kết quả `String` sang các thành phần/luồng khác bằng cơ chế công bố phù hợp.

Ví dụ:

Tệp `BuilderSnapshotDemo.java`:

```java
public class BuilderSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Hi");
        String snapshot = builder.toString();

        builder.append(" there");

        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);
        System.out.println("equalContents=" +
                builder.toString().equals(snapshot));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
```

Kết quả:

```text
builder=Hi there
snapshot=Hi
equalContents=false
```

`snapshot` không phải một “cửa sổ sống” vào builder. Nó giữ giá trị chuỗi tại thời điểm gọi `toString()`. Nếu builder sau đó đổi nội dung, `snapshot` không đổi.

Bản thân `String` bất biến thuận tiện để chia sẻ; tuy nhiên, ứng dụng vẫn cần **cơ chế truyền/công bố tham chiếu đúng** khi tổ chức đa luồng (ví dụ `Thread.start`, kết quả task `Future`, hàng đợi đồng thời, `volatile` hay đồng bộ tùy trường hợp). Không nên lấy tính bất biến làm lý do bỏ qua hoàn toàn các quy tắc công bố trong Java Memory Model.

## 10. `StringBuffer` giúp được gì, và vẫn giới hạn ở đâu?

`StringBuffer` là lớp mutable tương tự `StringBuilder` nhưng các phương thức chính được đồng bộ hóa. Khi thực sự cần một vùng đệm dùng chung với nhiều thao tác được đồng bộ ở mức phương thức, `StringBuffer` có thể là lựa chọn phù hợp.

Tuy nhiên, **đồng bộ từng phương thức không làm toàn bộ chuỗi hành động trở thành một thao tác nguyên tử**. Ví dụ logic:

```java
// Mã minh họa logic KHÔNG nguyên tử:
if (buffer.length() < 100) {
    buffer.append("data");
}
```

Nếu `buffer` là `StringBuffer` và nhiều luồng đồng thời thực thi, một luồng có thể đọc độ dài, rồi luồng khác thay đổi nội dung trước lần `append` tiếp theo. Muốn cả hai bước **kiểm tra + cập nhật** là một giao dịch đồng nhất, cần bảo vệ chúng bằng cùng một vùng đồng bộ hoặc thiết kế cấu trúc xử lý khác.

Có thể phối hợp bên ngoài:

```java
synchronized (buffer) {
    if (buffer.length() < 100) {
        buffer.append("data");
    }
}
```

Đây là fragment minh họa bên trong một phương thức với `buffer` đã khai báo. Khi dùng giải pháp khóa ngoài, mọi nơi tham gia thao tác tổng hợp phải dùng một quy ước phù hợp.

Cũng không nên diễn giải “`StringBuffer` là synchronized” thành “mọi kiểu sử dụng nhiều luồng đều luôn cho nội dung đúng theo yêu cầu nghiệp vụ”. **Tính thread-safe từng thao tác** và **tính nguyên tử của cả quy trình** là hai mức bảo đảm khác nhau.

## 11. So sánh khi builder bị thay đổi đồng thời

Một chương trình có thể tránh các phép `append` đua nhau bằng cách chỉ một luồng ghi, nhưng vẫn mắc lỗi khi **luồng đọc** gọi `compareTo` hoặc `toString()` không được phối hợp với luồng ghi.

Giả sử:

- Luồng A đang sửa `StringBuilder orderCode`.
- Luồng B gọi `orderCode.compareTo(expected)` để quyết định có khớp hay không.

Nếu không có đồng bộ/happens-before phù hợp, luồng B không được bảo đảm nhận một nội dung nhất quán. Việc `compareTo` tự nó chỉ đọc không khiến toàn bộ đối tượng trở thành thread-safe. Đừng xây dựng logic kiểm tra hoặc điều kiện bảo mật từ một snapshot có thể bị cập nhật đồng thời.

Các cách thiết kế thường đáng cân nhắc:

- Chuyển nội dung thành một `String` bất biến dưới đồng bộ rồi so sánh snapshot.
- Chỉ cho **một luồng sở hữu** builder; các luồng khác trao đổi qua các thông điệp/giá trị bất biến.
- Nếu cần thật sự truy cập builder chung, dùng khóa nhất quán cho quá trình đọc, sửa và so sánh.
- Khi chỉ cần ghép các đoạn độc lập, để mỗi luồng xây dựng đoạn riêng rồi kết hợp kết quả tại một nơi.

Đây là giới hạn về **truy cập đối tượng mutable**, không phải một lỗi riêng của `equals` hoặc `compareTo`.

## 12. Lưu ý với Unicode và việc sắp xếp theo `compareTo`

`StringBuilder` lưu dãy UTF-16 code unit. Thứ tự từ điển của `compareTo` dựa trên **đơn vị mã UTF-16**; đây không phải thứ tự từ điển tự nhiên của mọi ngôn ngữ và cũng không có ý nghĩa phân đoạn grapheme cluster.

Ví dụ chữ viết hoa/thường:

```java
StringBuilder upper = new StringBuilder("A");
StringBuilder lower = new StringBuilder("a");

System.out.println(upper.compareTo(lower) < 0); // true
System.out.println(upper.compareTo(lower) == 0); // false
```

Vì các code unit của `A` và `a` khác nhau, kết quả không bằng 0. `compareTo` cũng không tự bỏ dấu, chuẩn hóa Unicode hay áp dụng `Locale` cụ thể.

Khi cần **sắp xếp văn bản cho người dùng**, phải xác định các yêu cầu ngôn ngữ và hiển thị trước; có thể chuyển builder sang `String` và dùng `java.text.Collator` với locale thích hợp, hoặc một giải pháp chuẩn hóa/collation khác theo yêu cầu. Khi chỉ cần kiểm tra cùng nội dung UTF-16, `a.compareTo(b) == 0` là cách biểu đạt phù hợp cho hai builder đơn luồng/ổn định, nhưng không biến `equals` của builder thành phép so sánh nội dung.

## 13. Những lỗi phổ biến

**Lỗi 1 — Dùng `a.equals(b)` để so sánh hai `StringBuilder` cùng nội dung.** `StringBuilder` kế thừa `Object.equals`, nên hai đối tượng khác nhau trả `false`. Dùng `compareTo(b) == 0` khi cả hai là builder hoặc chụp `String` rồi so nội dung.

**Lỗi 2 — Hiểu `compareTo(b) == 0` là `a.equals(b) == true`.** Với builder, hai biểu thức **không tương đương**. Natural ordering của builder được ghi nhận là không nhất quán với `equals`.

**Lỗi 3 — Giả định `HashSet<StringBuilder>` sẽ loại các giá trị văn bản trùng nhau.** `HashSet` dùng `hashCode` và `equals` của đối tượng builder; hai builder có cùng nội dung vẫn là hai phần tử riêng.

**Lỗi 4 — Giả định `TreeSet<StringBuilder>` và `HashSet<StringBuilder>` có cùng khái niệm trùng nhau.** `TreeSet` dùng thứ tự tự nhiên, nên hai builder có `compareTo == 0` được xem là tương đương, trái với phép `equals`.

**Lỗi 5 — Sửa builder sau khi đưa làm khóa của `TreeSet` hoặc `TreeMap`.** Nội dung thay đổi có thể phá vỡ bất biến về thứ tự; chuyển sang `String` bất biến trước khi dùng làm khóa.

**Lỗi 6 — Dùng một `StringBuilder` chung để nhiều luồng gọi `append` mà không đồng bộ.** Đây là data race; không thể dựa vào kết quả đúng dù có thể thử vài lần không thấy lỗi.

**Lỗi 7 — Chỉ khóa luồng ghi rồi để luồng khác tự do đọc hoặc so sánh.** Việc đọc/trích xuất snapshot cũng phải tham gia quy ước đồng bộ nếu cùng builder đang thay đổi.

**Lỗi 8 — Nghĩ `StringBuffer` khiến một loạt bước kiểm tra và cập nhật trở thành nguyên tử.** Phương thức synchronized riêng lẻ không đảm bảo tổ hợp nhiều phương thức có tính nguyên tử.

**Lỗi 9 — Dùng `compareTo` để sắp xếp theo tiếng Việt hoặc văn bản tự nhiên mà không xét locale.** `compareTo` là so sánh mã UTF-16, không thay thế collation theo ngôn ngữ.

**Lỗi 10 — Giữ builder mutable để chia sẻ khi chỉ cần gửi một kết quả văn bản.** Tạo `String` snapshot thường đơn giản và an toàn hơn, đồng thời cần công bố tham chiếu đúng giữa các luồng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai builder riêng biệt cùng chứa `"java"` thì `equals` và `compareTo` trả về điều gì?

**Đáp án:** `a.equals(b)` là `false` vì khác đối tượng, còn `a.compareTo(b) == 0` là `true` vì cùng nội dung.

**Câu 2.** Vì sao `HashSet<StringBuilder>` có thể chứa hai builder cùng văn bản trong khi `TreeSet<StringBuilder>` chỉ giữ một?

**Đáp án:** `HashSet` dùng `Object.equals`/`hashCode` theo danh tính builder; `TreeSet` dùng `compareTo` theo nội dung để xác định tương đương.

**Câu 3.** Có nên thay đổi nội dung builder sau khi chèn nó vào `TreeSet` không?

**Đáp án:** Không. Thứ tự phần tử dựa vào nội dung tại thời điểm chèn, và cây không tự tái sắp xếp khi bạn sửa builder. Hãy dùng khóa kiểu `String` bất biến.

**Câu 4.** Hai luồng cùng `append` vào một `StringBuilder` có bảo đảm không mất dữ liệu không?

**Đáp án:** Không. Các thao tác trên `StringBuilder` không được đồng bộ hóa; phải tránh chia sẻ mutable builder hoặc dùng khóa/phối hợp phù hợp cho mọi truy cập liên quan.

**Câu 5.** `StringBuffer` có bảo đảm cặp hành động `length()` rồi `append()` luôn nguyên tử không?

**Đáp án:** Không. Đồng bộ hóa từng phương thức không tự ghép hai lời gọi thành một giao dịch. Muốn “kiểm tra rồi cập nhật” nguyên tử phải tổ chức đồng bộ bên ngoài hoặc dùng cấu trúc khác.

**Câu 6.** Nếu gọi `String snapshot = builder.toString();` rồi `builder.append("!")`, nội dung `snapshot` có đổi theo không?

**Đáp án:** Không. `snapshot` là `String` bất biến chứa nội dung tại thời điểm được tạo; nó không tham chiếu đến builder như một góc nhìn có thể thay đổi.

**Ghi nhớ:** `StringBuilder.equals` so **danh tính**, `StringBuilder.compareTo` (Java 11+) so **nội dung theo thứ tự từ điển** và hai hợp đồng này không nhất quán với nhau. `StringBuilder` là **mutable, không synchronized**: ưu tiên sở hữu trong một luồng, dùng `String` snapshot khi cần chia sẻ giá trị, và bảo vệ mọi truy cập chung bằng cơ chế đồng bộ thống nhất nếu thực sự cần dùng đa luồng.
