# Phân biệt danh tính, giá trị và thứ tự của đối tượng trong Java

Khi làm việc với một object, ba câu hỏi tưởng giống nhau thực ra có ý nghĩa khác nhau:

1. **Danh tính (identity):** Hai biến có trỏ đến **cùng một object** trong bộ nhớ hay không?
2. **Giá trị (value equality):** Hai object có được xem là **tương đương theo quy tắc của kiểu dữ liệu hoặc nghiệp vụ** hay không?
3. **Thứ tự (ordering):** Object nào đứng trước, đứng sau hoặc ngang hàng **theo tiêu chí sắp xếp**?

Trong Java, ba khái niệm này lần lượt liên quan đến `==`, `equals()`/`hashCode()` và `Comparable`/`Comparator`. Chọn nhầm có thể làm `HashSet`, `HashMap`, `TreeSet`, `TreeMap` hoạt động khác mong đợi.

## 1. Bảng phân biệt

| Khía cạnh | Câu hỏi | Công cụ | Kết quả |
|---|---|---|---|
| Identity | Có phải cùng một object? | `a == b` với hai tham chiếu | `boolean` |
| Equality | Có cùng giá trị theo định nghĩa của kiểu? | `a.equals(b)`, `Objects.equals(a,b)` | `boolean` |
| Băm giá trị | Hai giá trị bằng nhau có cùng mã băm? | `hashCode()` đi cùng `equals()` | `int`, không phải phép thử bằng nhau |
| Thứ tự tự nhiên | Đối tượng nào đứng trước theo mặc định? | `Comparable<T>.compareTo(T)` | Số âm, `0`, số dương |
| Thứ tự tùy chọn | Đối tượng nào đứng trước theo tiêu chí được chọn? | `Comparator<T>.compare(a,b)` | Số âm, `0`, số dương |

**`a == b`, `a.equals(b)` và `compare(a,b) == 0` không mặc nhiên tương đương.** Hai sách có thể là hai instance khác nhau nhưng cùng thông tin; hai sách khác nhau có thể được xếp ngang nhau khi comparator chỉ xét năm xuất bản.

## 2. Danh tính: cùng object hay khác object?

Với **kiểu tham chiếu**, `==` trả `true` khi hai biến trỏ đến cùng instance (hoặc cả hai đều `null`). Phép này không đọc thuộc tính bên trong object.

~~~java
String first = new String("java");
String second = new String("java");
String alias = first;

System.out.println(first == second);      // false
System.out.println(first == alias);       // true
System.out.println(first.equals(second)); // true
~~~

Đây là **đoạn mã minh họa** có thể đặt trong `main`, không phải một file Java độc lập. Hai lần `new String` tạo hai instance; `alias` trỏ đến cùng instance với `first`. `String.equals` so sánh chuỗi ký tự nên hai instance vẫn bằng nhau về nội dung.

Với **kiểu nguyên thủy** (`int`, `boolean`, `char`...), `==` so sánh giá trị nguyên thủy. Đừng dùng kết quả tình cờ của string interning hay bộ nhớ đệm wrapper (`Integer`) để suy ra rằng `==` so sánh nội dung object: các cơ chế này có thể tái sử dụng instance trong một số trường hợp.

Identity hữu ích khi thuật toán thật sự cần biết **cùng đối tượng trong bộ nhớ**, chẳng hạn kiểm tra alias hoặc duyệt đồ thị đối tượng theo identity. `IdentityHashMap` là cấu trúc chuyên biệt dùng identity cho khóa; `HashMap` thông thường dùng equality theo giá trị. `System.identityHashCode(x)` có ích khi chẩn đoán nhưng **không phải ID duy nhất** và không chứng minh hai object giống nhau, vì vẫn có thể xảy ra va chạm hash.

## 3. Giá trị: `equals()` và `hashCode()`

`Object.equals()` mặc định có nghĩa như identity. Các kiểu như `String`, `BigDecimal` và nhiều value object định nghĩa lại equality theo nội dung. Cần quyết định rõ **thuộc tính nào tham gia định nghĩa bằng nhau**:

- **Value object** như tọa độ hoặc một lượng tiền: thường bằng nhau khi mọi thành phần có ý nghĩa đều bằng nhau; tính bất biến giúp sử dụng làm khóa.
- **Entity** như đơn hàng: thường cần phân biệt theo mã định danh ổn định; trường mô tả có thể thay đổi mà entity vẫn là một. Phải cẩn thận với ID chưa gán hoặc có thể đổi.
- **`record`**: Java tự sinh `equals()`/`hashCode()` từ các component. Record **không tự sinh `Comparable`**. Nếu component là array, so sánh component đó vẫn theo equality mặc định của array (identity), không tự so sánh sâu từng phần tử.

Hợp đồng của `equals()` yêu cầu:

1. **Phản xạ:** `x.equals(x)` luôn đúng.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu:** `x.equals(y)` và `y.equals(z)` đúng thì `x.equals(z)` phải đúng.
4. **Nhất quán:** khi dữ liệu dùng để xét equality không thay đổi, các lần gọi có cùng kết quả.
5. **Khác `null`:** với `x` khác `null`, `x.equals(null)` trả `false`.

Nếu `a` có thể `null`, gọi `a.equals(b)` sẽ có nguy cơ `NullPointerException`; dùng `Objects.equals(a,b)` cho so sánh an toàn với `null`. Khi tự triển khai equality, `Objects.equals` có thể hỗ trợ các trường, còn `Arrays.equals`/`Arrays.deepEquals` hữu ích nếu cần so sánh nội dung mảng.

### Vì sao `hashCode()` đi cùng `equals()`?

Quy tắc bắt buộc là: **nếu `x.equals(y)` thì `x.hashCode() == y.hashCode()`.** Chiều ngược lại không bắt buộc: hai object khác nhau vẫn có thể trùng hash. Khi ghi đè `equals()` phải ghi đè `hashCode()` tương ứng. Các collection dựa trên hash sử dụng hash để chọn vùng tra cứu và equality để phân biệt khóa cụ thể.

Nếu object đã nằm trong `HashSet` hoặc làm khóa `HashMap`, việc đổi các trường tham gia equality/hash có thể khiến tra cứu hoặc xóa không tìm được phần tử nữa. Ưu tiên dùng khóa bất biến. Với kế thừa, thiết kế equality cần tránh phá tính đối xứng hoặc bắc cầu.

## 4. Thứ tự: `Comparable` và `Comparator`

Kết quả của phép so sánh thứ tự chỉ cần xét **dấu**:

- **Âm:** vế trái đứng trước vế phải.
- **`0`:** hai vế ngang hàng **theo tiêu chí sắp xếp**.
- **Dương:** vế trái đứng sau vế phải.

Không được giả định kết quả chỉ là `-1`, `0` hoặc `1`.

**`Comparable<T>`** được cài trong kiểu qua `compareTo` khi kiểu có một thứ tự tự nhiên hợp lý. **`Comparator<T>`** là quy tắc bên ngoài, có thể chọn khác nhau tại từng điểm dùng: theo tên, theo tuổi, theo giá... Ví dụ một comparator tăng theo độ dài chuỗi, rồi tăng theo chữ cái nếu bằng độ dài:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());

System.out.println(byLengthThenText.compare("an", "be") < 0);  // true
System.out.println(byLengthThenText.compare("a", "bbb") < 0); // true
~~~

Đây là đoạn minh họa đặt trong `main` với `import java.util.Comparator;`. Phương thức `thenComparing` giúp **phá hòa** khi tiêu chí đầu bằng nhau. Có thể dùng `reversed()`, `nullsFirst`, `nullsLast`, `comparingInt`, `comparingLong` khi phù hợp. Nếu giá trị có thể `null`, phải chọn chính sách rõ ràng thay vì để comparator tự ném exception ngoài ý muốn.

Hợp đồng thứ tự yêu cầu dấu của `compare(a,b)` đảo so với `compare(b,a)`, quan hệ trước/sau có tính **bắc cầu**, và khi `compare(a,b) == 0`, so sánh `a` và `b` với cùng một `z` phải có cùng dấu. Tránh `return a.score - b.score;` vì phép trừ có thể tràn `int`; dùng `Integer.compare(a.score, b.score)` hoặc `Comparator.comparingInt(...)`.

## 5. Một chương trình Java 17 chứng minh cả ba khái niệm

Trong ví dụ này, `Book` là record có equality theo cả `isbn` và `title`. Thứ tự tự nhiên cũng xét đúng hai thành phần đó, nên **với Book**, `compareTo(...) == 0` nhất quán với `equals()`. `Ticket` dùng comparator ngoài để minh họa một bộ so sánh có thể gom hai object khác nhau vào cùng nhóm thứ tự. Cuối cùng, `BigDecimal` cho thấy ngoại lệ của một thứ tự tự nhiên không nhất quán với `equals()`.

Lưu chương trình đầy đủ dưới tên **`ObjectContractDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class ObjectContractDemo {
    record Book(String isbn, String title) implements Comparable<Book> {
        @Override
        public int compareTo(Book other) {
            return Comparator.comparing(Book::isbn)
                    .thenComparing(Book::title)
                    .compare(this, other);
        }
    }

    record Ticket(String id, int priority) {}

    public static void main(String[] args) {
        Book first = new Book("978-1", "Java");
        Book equalValue = new Book("978-1", "Java");
        Book other = new Book("978-2", "Concurrency");

        System.out.println("Book ==: " + (first == equalValue));
        System.out.println("Book equals: " + first.equals(equalValue));
        System.out.println("Book hash equals: "
                + (first.hashCode() == equalValue.hashCode()));
        System.out.println("Book compare = 0: "
                + (first.compareTo(equalValue) == 0));
        System.out.println("Book first < other: "
                + (first.compareTo(other) < 0));
        System.out.println("HashSet<Book>: "
                + new HashSet<>(List.of(first, equalValue, other)).size());
        System.out.println("TreeSet<Book>: "
                + new TreeSet<>(List.of(first, equalValue, other)).size());

        Ticket a = new Ticket("A", 1);
        Ticket b = new Ticket("B", 1);
        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);
        TreeSet<Ticket> byPrioritySet = new TreeSet<>(byPriority);
        byPrioritySet.add(a);
        byPrioritySet.add(b);
        System.out.println("Ticket equals: " + a.equals(b));
        System.out.println("Ticket compare = 0: "
                + (byPriority.compare(a, b) == 0));
        System.out.println("TreeSet priority only: " + byPrioritySet.size());

        Comparator<Ticket> byPriorityThenId =
                byPriority.thenComparing(Ticket::id);
        TreeSet<Ticket> distinctTickets = new TreeSet<>(byPriorityThenId);
        distinctTickets.add(a);
        distinctTickets.add(b);
        System.out.println("TreeSet priority + id: "
                + distinctTickets.size());

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("BigDecimal equals: " + x.equals(y));
        System.out.println("BigDecimal compare = 0: "
                + (x.compareTo(y) == 0));
        System.out.println("HashSet<BigDecimal>: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet<BigDecimal>: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ObjectContractDemo.java
java ObjectContractDemo
~~~

Đầu ra:

~~~text
Book ==: false
Book equals: true
Book hash equals: true
Book compare = 0: true
Book first < other: true
HashSet<Book>: 2
TreeSet<Book>: 2
Ticket equals: false
Ticket compare = 0: true
TreeSet priority only: 1
TreeSet priority + id: 2
BigDecimal equals: false
BigDecimal compare = 0: true
HashSet<BigDecimal>: 2
TreeSet<BigDecimal>: 1
~~~

**Phân tích kết quả:**

1. `first` và `equalValue` là hai instance (`== false`) nhưng bằng nhau về giá trị. Record tạo `equals` và `hashCode` tương ứng; `compareTo` của `Book` cũng trả `0`.
2. `HashSet<Book>` dựa vào equality/hash; `TreeSet<Book>` dựa vào natural ordering. Cả hai giữ đúng hai sách phân biệt.
3. Hai `Ticket` có ID khác nhau nên `equals` là `false`, nhưng comparator chỉ nhìn `priority` nên trả `0`. `TreeSet` xem chúng như **một khóa** và chỉ giữ một phần tử. Khi phá hòa thêm `id`, cả hai được giữ lại.
4. `BigDecimal("2.0")` khác `BigDecimal("2.00")` theo `equals`, vì `equals` xét cả **scale** (1 so với 2). Tuy nhiên `compareTo` so giá trị số nên trả `0`. Vì vậy hash set giữ 2, còn tree set giữ 1. **Thứ tự tự nhiên của `BigDecimal` nổi tiếng là không nhất quán với `equals`.**

## 6. `compare == 0` không đồng nghĩa cùng giá trị

Comparator xác định các **nhóm tương đương theo sắp xếp**. Một bộ so sánh chỉ theo điểm thi có thể xem hai sinh viên khác mã là ngang hàng. Điều này không sai khi dùng để sắp xếp một danh sách nhưng ảnh hưởng lớn nếu dùng comparator làm định nghĩa khóa.

| Cấu trúc/thao tác | Quy tắc equality hoặc thứ tự |
|---|---|
| `HashSet`, `HashMap` | `equals()` kết hợp `hashCode()` |
| `TreeSet`, `TreeMap` | `compareTo()` hoặc `Comparator.compare()`; `0` là cùng khóa |
| `List.sort()`, `Collections.sort()`, `Stream.sorted()` | Sắp theo comparator, **không tự loại các phần tử ngang hàng** |
| `List.contains()` | Kiểm tra bằng `equals()` |

Với những object dùng làm khóa trong sorted set/map, **nên** chọn thứ tự nhất quán với equality nếu khả thi: `compare(a,b) == 0` khi và chỉ khi `a.equals(b)`. Nếu cố ý dùng comparator để gom các nhóm theo điểm hoặc mức ưu tiên, hãy mô tả rõ ý nghĩa đó và chấp nhận rằng set/map chỉ giữ một khóa trong mỗi nhóm.

Tính nhất quán phải xét cả những object có **cùng equality nhưng khác dữ liệu dùng để sắp xếp**. Ví dụ nếu equality của entity chỉ xét ID, comparator theo `name` rồi ID chưa chắc nhất quán: hai bản thể có cùng ID nhưng tên khác nhau có thể cho kết quả khác `0`. Khi thiết kế cơ chế khóa, phải quyết định liệu entity có bất biến và theo những trường nào.

Không thay đổi trường tham gia comparator khi object đang nằm trong `TreeSet`/`TreeMap`: vị trí sắp xếp của node đã được xây dựng từ giá trị cũ, khiến tra cứu, xóa hoặc phát hiện trùng khó tin cậy.

## 7. Cách chọn trong tình huống thực tế

| Yêu cầu | Phép/thiết kế phù hợp | Điều cần lưu ý |
|---|---|---|
| Kiểm tra cùng instance | `a == b` | Chỉ là identity với tham chiếu |
| So nội dung chuỗi hoặc value object | `Objects.equals(a,b)` | An toàn khi có `null` |
| Tạo khóa cho hash map/set | `equals` + `hashCode` cùng logic | Trường khóa nên bất biến |
| Sắp theo thứ tự mặc định | `Comparable` | Không phải mọi kiểu đều có natural ordering |
| Sắp theo nhiều tiêu chí chọn lúc chạy | `Comparator`, `thenComparing` | Phá hòa nếu cần trật tự xác định |
| Giữ nhiều phần tử có cùng điểm trong `List` | `List.sort(comparator)` | Không cần phá hòa để giữ phần tử |
| Giữ nhiều phần tử trong `TreeSet` | Comparator phân biệt theo khóa phù hợp | `compare == 0` bị coi là một phần tử |
| So độ lớn `BigDecimal` bỏ qua scale | `compareTo(...) == 0` | `equals` xét scale |
| So nội dung các mảng | `Arrays.equals` hoặc `Arrays.deepEquals` | `array.equals` mặc định so identity |

Quy trình thiết kế: **(1)** xác định entity hay value object; **(2)** định nghĩa trường tham gia equality; **(3)** giữ hợp đồng hash; **(4)** chọn thứ tự tự nhiên và/hoặc comparator; **(5)** kiểm tra xem quan hệ `compare == 0` có phù hợp với các collection định dùng hay không; **(6)** kiểm thử tính đối xứng, bắc cầu và tính ổn định của quy tắc.

## 8. Lỗi phổ biến cần tránh

1. **Dùng `==` để so hai `String` hoặc wrapper:** nhận kết quả phụ thuộc instance hoặc cơ chế cache thay vì nội dung.
2. **Override `equals` nhưng không override `hashCode`:** phá hợp đồng trong hash set/map.
3. **Coi hash trùng là giá trị bằng nhau:** hash collision là hợp lệ, không phải chứng minh equality.
4. **Chỉ so một trường không duy nhất trong comparator của `TreeSet`:** vô tình bỏ mất các phần tử khác nhau.
5. **So số nguyên bằng phép trừ:** overflow có thể đảo sai trật tự.
6. **Comparator không bắc cầu hoặc phụ thuộc dữ liệu đang đổi:** kết quả sắp xếp và cây có thể bất ổn, vi phạm hợp đồng.
7. **Sửa trường equality/hash/order của khóa đã thêm vào set/map:** có thể không tra cứu hoặc xóa được.
8. **Tưởng record luôn so sâu mảng:** component kiểu mảng vẫn có equality mặc định theo tham chiếu.
9. **Coi `compareTo == 0` luôn bằng `equals == true`:** phản ví dụ điển hình là `BigDecimal`.

## 9. Câu hỏi tự kiểm tra

**1.** Hai biến cùng trỏ đến một instance; giá trị của một trường mutable thay đổi. Kết quả `==` giữa hai biến có thay đổi không?  
**Đáp án:** Không. Chúng vẫn trỏ cùng object; equality với object *khác* có thể đổi tùy cách triển khai.

**2.** `a.equals(b) == false` nhưng hai `hashCode()` bằng nhau có hợp lệ không?  
**Đáp án:** Có, vì hash collision được phép. Chiều bắt buộc là equality đúng thì hash phải bằng nhau.

**3.** Hai đơn hàng có ID khác nhau nhưng cùng ngày tạo, comparator chỉ xét ngày và trả `0`. Thêm cả hai vào `TreeSet` thì sao?  
**Đáp án:** Set chỉ giữ một phần tử theo comparator; muốn phân biệt theo ID thì cần tiêu chí bổ sung phù hợp.

**4.** Muốn sắp danh sách nhân viên theo tuổi nhưng vẫn giữ tất cả người cùng tuổi, có bắt buộc phá hòa theo ID không?  
**Đáp án:** Không. Sắp xếp `List` không loại phần tử. Phá hòa cần khi muốn thứ tự xác định giữa các trường hợp cùng tuổi, hoặc khi dùng comparator làm nghĩa của khóa trong sorted set/map.

**Ghi nhớ:** **Identity** trả lời *cùng object?*; **equality** trả lời *cùng giá trị theo quy tắc nào?*; **ordering** trả lời *đứng trước/sau/ngang hàng theo tiêu chí gì?* Thiết kế và kiểm thử từng quan hệ riêng biệt.
