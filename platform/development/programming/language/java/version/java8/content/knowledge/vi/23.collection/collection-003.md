# List.replaceAll và biến đổi tại chỗ trong Java

**Chủ đề:** Java 8 → Collection → List.replaceAll và biến đổi tại chỗ.

Khi có một danh sách tên, điểm số, mã hàng hoặc đối tượng nghiệp vụ, đôi khi ta muốn **thay giá trị của từng phần tử ngay trong danh sách hiện có**, không tạo một danh sách kết quả mới. Từ Java 8, giao diện **java.util.List<E>** có phương thức **replaceAll(UnaryOperator<E>)** để thực hiện công việc này.

Điểm quan trọng nhất: **List.replaceAll biến đổi chính List đang được gọi**, bằng cách thay phần tử ở từng vị trí bằng kết quả của một hàm. Nó **không tạo hay trả về List mới**, không phải **Stream.map(...)**, và không có nghĩa là một đối tượng đang nằm trong List tự thay đổi nội dung bên trong.

Các API được trình bày vẫn áp dụng trong Java hiện đại. Mã chạy độc lập ưu tiên **Java 17+**. Trong ví dụ có sử dụng **List.of(...)** (Java 9+), **Stream.toList()** (Java 16+) và **record** (Java 16+); đây là cú pháp phụ trợ hiện đại, không phải phần của Java 8 ban đầu.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích chính xác chữ ký **List.replaceAll(UnaryOperator<E>)** và ý nghĩa của "biến đổi tại chỗ" (in-place).
2. Dùng lambda hoặc method reference để chuẩn hóa chuỗi, cập nhật giá trị số và thay đối tượng bằng phiên bản mới.
3. Phân biệt thay phần tử trong **List** với thay đổi trạng thái **bên trong đối tượng** được List giữ tham chiếu.
4. Hiểu khác biệt giữa **List.replaceAll(...)**, **Stream.map(...).toList()**, **Collections.replaceAll(...)**, **List.set(...)**, **sort(...)** và **removeIf(...)**.
5. Biết những triển khai List nào hỗ trợ thay phần tử, đặc biệt **ArrayList**, **LinkedList**, **Arrays.asList**, **List.of** và **subList**.
6. Tránh các lỗi với **null**, exception giữa chừng, list unmodifiable, tác dụng phụ trong operator và xử lý đồng thời.

## 2. Chữ ký API và cơ chế cơ bản

Phương thức được khai báo trên giao diện List:

~~~java
default void replaceAll(UnaryOperator<E> operator)
~~~

Đây là **chữ ký API minh họa**, không phải một chương trình Java độc lập. **UnaryOperator<E>** thuộc **java.util.function** và là trường hợp chuyên biệt của **Function<E, E>**: nhận một giá trị kiểu E và trả một giá trị **cũng có kiểu E**.

Hình thức logic:

~~~text
List<E> ban đầu:
vị trí:   0      1      2
giá trị:  A      B      C

operator: E -> E

List<E> sau replaceAll:
vị trí:   0        1        2
giá trị:  f(A)     f(B)     f(C)

Vẫn là chính đối tượng List ban đầu.
~~~

Các đặc điểm:

- **Trả về void**: không thể viết **List<E> result = list.replaceAll(...)**.
- **Không thêm/bớt phần tử** theo hợp đồng thay thế thông thường: số phần tử và vị trí chỉ số không đổi, còn **giá trị tại mỗi vị trí** được thay bằng kết quả operator.
- **Áp dụng lên từng phần tử**, không chỉ những giá trị bằng một giá trị cũ cụ thể.
- **Kiểu phần tử không thay đổi ở cấp generic E**: ví dụ List<String> không thể trực tiếp thay thành List<Integer> bằng replaceAll.
- **Tác động thấy được qua các tham chiếu cùng trỏ tới List** vì List được sửa tại chỗ.
- **Không đảm bảo hoạt động trên mọi List**: thay thế phần tử là optional operation của List; một số triển khai unmodifiable/fixed-rule có thể ném ngoại lệ.

Một ví dụ ngắn (minh họa, cần import List và ArrayList):

~~~java
List<Integer> scores = new ArrayList<>(List.of(5, 10, 15));
scores.replaceAll(score -> score * 2);

// scores == [10, 20, 30]
~~~

**Hàm score -> score * 2** nhận từng giá trị kiểu Integer và trả Integer mới (thông qua unboxing/boxing của phép toán số). List đang giữ ba phần tử; sau replaceAll vẫn giữ ba vị trí đó.

### 2.1. Default implementation của List

Theo hợp đồng API hiện hành, cách cài đặt mặc định tương đương với việc lấy **ListIterator** và thực hiện **set** ở từng vị trí:

~~~java
ListIterator<E> iterator = list.listIterator();

while (iterator.hasNext()) {
    iterator.set(operator.apply(iterator.next()));
}
~~~

Đây là **mã minh họa bằng các kiểu generic**, cần có biến **list** và kiểu **E** để biên dịch; không phải đoạn mã được phép chép nguyên vào một class thông thường.

Cơ chế ý niệm là:

1. **next()** đọc phần tử hiện tại.
2. **operator.apply(value)** tính giá trị thay thế.
3. **iterator.set(replacement)** ghi giá trị đó tại vị trí vừa đọc.
4. Tiếp tục cho tới hết phần tử.

Nếu ListIterator của một List **không hỗ trợ set(...)**, default implementation có thể ném **UnsupportedOperationException** khi cần thay phần tử đầu tiên. Một số lớp, như **ArrayList**, có thể override replaceAll để tối ưu; không nên suy luận chi tiết quản lý iterator hoặc các hiệu ứng ngoài hợp đồng từ mã mặc định cho mọi implementation.

**Không nhầm replaceAll với một transaction:** API không cung cấp commit/rollback tự động nếu operator hoặc thao tác set gặp lỗi giữa chừng.

## 3. Ví dụ hoàn chỉnh: đổi số, chuẩn hóa chuỗi và so với Stream.map

Lưu vào **ListReplaceAllDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ListReplaceAllDemo {
    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(
                List.of(1, 2, 3)
        );

        List<Integer> alias = numbers;

        numbers.replaceAll(n -> Math.multiplyExact(n, 2));

        System.out.println("numbers=" + numbers);
        System.out.println("sameInstance=" + (alias == numbers));
        System.out.println("alias=" + alias);

        List<String> names = new ArrayList<>(
                List.of("  an ", "binh", " CHI ")
        );

        names.replaceAll(name ->
                name.trim().toUpperCase(Locale.ROOT)
        );

        System.out.println("names=" + names);

        List<String> source = new ArrayList<>(
                List.of("a", "b")
        );

        List<String> mapped = source.stream()
                .map(s -> s + "!")
                .toList();

        System.out.println("source=" + source);
        System.out.println("mapped=" + mapped);
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac -encoding UTF-8 ListReplaceAllDemo.java
java ListReplaceAllDemo
~~~

**Stdout chính xác:**

~~~text
numbers=[2, 4, 6]
sameInstance=true
alias=[2, 4, 6]
names=[AN, BINH, CHI]
source=[a, b]
mapped=[a!, b!]
~~~

Giải thích:

- **numbers.replaceAll(...)** thay ba phần tử tại các vị trí hiện có. **alias == numbers** là true vì hai biến trỏ đến cùng đối tượng List.
- **Math.multiplyExact** phát hiện tràn phép nhân kiểu nguyên thay vì im lặng tạo giá trị sai. Trong dữ liệu ví dụ không xảy ra tràn.
- **names.replaceAll(...)** bỏ khoảng trắng hai đầu và chuyển chữ hoa. **Locale.ROOT** làm rõ quy tắc chuyển chữ hoa độc lập với locale mặc định của môi trường; lựa chọn locale thực tế còn tùy ngôn ngữ/nghiệp vụ.
- **source.stream().map(...).toList()** xây dựng một danh sách kết quả riêng. **source** không bị replaceAll và vẫn là **[a, b]**.
- **Stream.toList()** trả List không cho phép sửa. Nếu muốn một List kết quả có thể cập nhật tiếp, dùng **new ArrayList<>(source.stream().map(...).toList())** hoặc collector phù hợp.

**Nhắc lại:** cách Stream ở đây không sửa source vì lambda **s -> s + "!"** không có tác dụng phụ. Nếu viết lambda có chủ ý sửa đối tượng bên trong, Stream API không tự ngăn các tác dụng phụ đó; hãy giữ mapper thuần khi mục đích là tạo dữ liệu kết quả mới.

## 4. In-place thay phần tử, không nhất thiết sửa chính đối tượng phần tử

Danh sách của Java lưu **tham chiếu đến đối tượng** đối với kiểu tham chiếu. **replaceAll** thay giá trị/tham chiếu ở từng vị trí của List; nếu operator **trả về một đối tượng mới**, phần tử List trỏ sang đối tượng mới. **Đối tượng cũ không tự bị sửa**.

Ví dụ:

~~~java
record Item(String sku, long cents) {}

List<Item> items = new ArrayList<>(
        List.of(new Item("A", 1000))
);

Item old = items.get(0);

items.replaceAll(item ->
        new Item(item.sku(), Math.multiplyExact(item.cents(), 2))
);

// items.get(0).cents() == 2000
// old.cents() == 1000
~~~

Đây là **đoạn minh họa**: cần import **List**, **ArrayList** và khai báo record **Item** trong một vị trí hợp lệ (Java 17+). **record Item** bất biến về các trường, vì vậy tạo bản ghi mới là cách biểu đạt rõ ràng của phép biến đổi. Biến **old** vẫn trỏ đến bản ghi ban đầu.

Nếu một phần tử là **đối tượng mutable** và operator thay đổi trực tiếp trạng thái của nó rồi trả lại chính nó, thì tác dụng phụ sẽ hiện diện cả ở những nơi khác đang giữ tham chiếu tới đối tượng ấy. Đó là **mutation bên trong phần tử**, khác với **thay tham chiếu của phần tử trong List**.

Ví dụ ý niệm:

~~~java
// Không khuyến khích trộn các tác dụng phụ khó kiểm soát.
// Giả sử Person là một lớp mutable có setName và getName.
people.replaceAll(person -> {
    person.setName(person.getName().trim());
    return person;
});
~~~

Đoạn này **không độc lập** vì kiểu Person và biến people chưa được khai báo. Nó hoạt động bằng cách **sửa đối tượng Person**, chứ không phải tạo Person mới. Nếu đối tượng Person được chia sẻ với module khác, nơi đó cũng có thể thấy tên đã bị đổi.

**Ưu tiên operator thuần** (nhận giá trị, trả giá trị mới theo quy tắc rõ ràng), đặc biệt khi dữ liệu được chia sẻ. Trên đối tượng record/immutable, replaceAll với constructor hoặc phương thức tạo bản sao rõ nghĩa hơn tác dụng phụ lên object cũ.

## 5. Ví dụ nghiệp vụ: thay record tại từng vị trí

Giả sử danh sách bảng giá cần điều chỉnh giá cent bằng hệ số 2. Chọn một List có thể thay phần tử, dùng **record** để tránh sửa trạng thái nội bộ và dùng **Math.multiplyExact** để phát hiện tràn kiểu long.

Lưu vào **PriceUpdateDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PriceUpdateDemo {
    record Line(String sku, long cents) {}

    public static void main(String[] args) {
        List<Line> lines = new ArrayList<>(List.of(
                new Line("A", 1000),
                new Line("B", 2500)
        ));

        Line oldFirst = lines.get(0);

        lines.replaceAll(line ->
                new Line(
                        line.sku(),
                        Math.multiplyExact(line.cents(), 2L)
                )
        );

        System.out.println("lines=" + lines);
        System.out.println("oldFirst=" + oldFirst);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PriceUpdateDemo.java
java PriceUpdateDemo
~~~

**Stdout:**

~~~text
lines=[Line[sku=A, cents=2000], Line[sku=B, cents=5000]]
oldFirst=Line[sku=A, cents=1000]
~~~

**Điểm cần lưu ý khi ứng dụng thực tế:**

1. **replaceAll** cập nhật đúng **hai phần tử List**; không làm thay đổi các bản ghi Line cũ đang được nơi khác giữ tham chiếu.
2. Đơn vị tiền đã chọn là **cent**, tránh sai số nhị phân của double khi thao tác tiền có đơn vị nhỏ nhất cố định.
3. **Math.multiplyExact** kiểm tra overflow của từng phép tính. Nếu giữa chừng xảy ra lỗi, **replaceAll không có cơ chế rollback toàn bộ List**; cần thiết kế bước validate hoặc tính trước khi yêu cầu cập nhật phải toàn phần.
4. **record** chỉ đảm bảo các component reference không bị gán lại sau khi xây dựng, không tự biến các đối tượng mutable bên trong record thành immutable. Ở ví dụ này các component là String và long nên phù hợp.
5. Nếu giá thực tế cần thuế, tỷ giá hoặc quy tắc làm tròn phức tạp, cần mô hình dữ liệu phù hợp như BigDecimal và quy tắc nghiệp vụ riêng. **replaceAll** chỉ là cơ chế thay phần tử, không phải một hệ thống tính giá hoàn chỉnh.

## 6. List nào hỗ trợ replaceAll?

**replaceAll là optional operation của List**. Khả năng thay phần tử phụ thuộc implementation, không chỉ phụ thuộc kiểu khai báo **List<E>**.

| Nguồn tạo List | Có thể thay phần tử với replaceAll? | Lưu ý |
|---|---|---|
| **new ArrayList<>(...)** | Có | Có thể thêm/xóa và thay phần tử; không đồng nghĩa an toàn đồng thời |
| **new LinkedList<>(...)** | Có | ListIterator hỗ trợ thay phần tử |
| **Arrays.asList(array)** | Có | **Kích thước cố định**, backed by array; thay phần tử phản ánh ở mảng |
| **List.of(...)** | Không | List unmodifiable; thao tác thay phần tử ném UnsupportedOperationException |
| **List.copyOf(...)** | Không | Kết quả unmodifiable; không thể thay từng phần tử |
| **Collections.unmodifiableList(backing)** | Không qua view | View không cho thay qua nó; backing nếu mutable có thể được sửa riêng |
| **new ArrayList<>(List.of(...))** | Có | Tạo một List mới có thể sửa, sao chép các tham chiếu phần tử |
| **parent.subList(from, to)** | Tùy backing | Là view trên đoạn của parent, thay qua view có thể đổi parent |

**Từ "cố định kích thước" khác với "không thể sửa":** **Arrays.asList** không cho **add/remove** làm thay đổi độ dài, nhưng vẫn cho **set/replaceAll**. Ngược lại **List.of** không cho thay phần tử, ngay cả khi không thay kích thước.

### 6.1. Arrays.asList: List có kích thước cố định nhưng thay được phần tử

Lưu thành **ListImplementationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ListImplementationDemo {
    public static void main(String[] args) {
        Integer[] array = {1, 2, 3};

        List<Integer> fixed = Arrays.asList(array);
        fixed.replaceAll(x -> x * 10);

        System.out.println("fixed=" + fixed);
        System.out.println("array=" + Arrays.toString(array));

        try {
            fixed.add(40);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "fixedAdd=UnsupportedOperationException");
        }

        List<String> unmodifiable = List.of("a", "b");
        try {
            unmodifiable.replaceAll(String::toUpperCase);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "listOf=UnsupportedOperationException");
        }

        List<String> parent = new ArrayList<>(
                List.of("a", "b", "c", "d")
        );

        parent.subList(1, 3).replaceAll(
                s -> s.toUpperCase(Locale.ROOT)
        );

        System.out.println("parent=" + parent);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListImplementationDemo.java
java ListImplementationDemo
~~~

**Stdout:**

~~~text
fixed=[10, 20, 30]
array=[10, 20, 30]
fixedAdd=UnsupportedOperationException
listOf=UnsupportedOperationException
parent=[a, B, C, d]
~~~

Giải thích:

- **Arrays.asList(array)** trả List được hỗ trợ bởi **chính mảng đó**. Vì vậy replaceAll cập nhật giá trị trong array.
- **fixed.add(40)** thay đổi kích thước nên không được hỗ trợ.
- **List.of("a", "b")** là unmodifiable, nên **replaceAll** ném **UnsupportedOperationException**. Không nên bọc lời gọi này trong logic dựa vào trạng thái "có thay đổi hay không"; thao tác không được phép.
- **parent.subList(1, 3)** là view chỉ gồm phần tử tại vị trí **1 và 2**. ReplaceAll trên view làm **parent** thành **[a, B, C, d]**. **fromIndex** bao gồm, **toIndex** không bao gồm.

**Cẩn thận với subList:** Vì nó được backed by list gốc, không thay đổi cấu trúc list gốc (như add/remove ngoài view) trong lúc dùng view. Theo API, nếu backing list bị sửa cấu trúc không thông qua view, ngữ nghĩa của view có thể trở nên không xác định.

### 6.2. Muốn cập nhật một List lấy từ List.of?

Tạo bản sao mutable trước:

~~~java
List<String> source = List.of("an", "binh", "chi");

List<String> editable = new ArrayList<>(source);
editable.replaceAll(String::toUpperCase);

// editable == [AN, BINH, CHI]
// source == [an, binh, chi]
~~~

Đoạn minh họa cần import **List**, **ArrayList**. Đây là thao tác **sao chép List**, không phải deep copy toàn bộ đối tượng phần tử. Với String bất biến trong ví dụ, kết quả dễ hiểu; với đối tượng mutable, các bản sao List ban đầu vẫn giữ tham chiếu tới cùng các object cho tới khi phần tử được thay bởi object khác.

## 7. replaceAll so với Stream.map, List.set và các API liên quan

| API | Công việc chính | Sửa List nguồn? | Trả về |
|---|---|---|---|
| **list.replaceAll(UnaryOperator<E>)** | Tính giá trị mới cho **mọi vị trí**, thay ngay trong List | **Có**, nếu hỗ trợ | **void** |
| **list.set(index, value)** | Thay **một vị trí** cụ thể | **Có**, nếu hỗ trợ | Phần tử cũ E |
| **stream.map(Function<T,R>)** | Khai báo biến đổi dữ liệu trong pipeline | **Không theo ngữ nghĩa chuẩn**, nếu mapper thuần | **Stream<R>** |
| **source.stream().map(...).toList()** | Tạo **List kết quả mới** từ phép biến đổi | Không, nếu mapper thuần | List<R> không cho phép sửa |
| **Collections.replaceAll(list, old, new)** | Thay **những phần tử bằng old** bằng new | Có, nếu List hỗ trợ | **boolean** |
| **list.sort(comparator)** | Sắp xếp lại **thứ tự** các phần tử | Có, nếu hỗ trợ | **void** |
| **list.removeIf(predicate)** | **Xóa** các phần tử thỏa điều kiện | Có, nếu hỗ trợ | **boolean** |

### 7.1. Khi nào chọn replaceAll?

Chọn **replaceAll** khi:

- Bạn **chủ ý** cập nhật List đang có.
- Mỗi vị trí vẫn giữ một phần tử **cùng kiểu E**.
- List hỗ trợ thay phần tử; không cần thay số lượng phần tử.
- Người gọi hiểu hệ quả của việc mọi tham chiếu đến List đều nhìn thấy nội dung mới.
- Không có yêu cầu rollback tự động hoặc xử lý song song của chính thao tác này.

Chọn **Stream.map(...).toList()** hoặc collector khi:

- Muốn **giữ List nguồn không đổi**.
- Muốn đổi kiểu, ví dụ **String → Integer**, hoặc xây dựng List bất biến.
- Muốn sử dụng pipeline nhiều bước **filter/map/sorted** mà không sửa nguồn.
- Muốn tránh hiệu ứng phụ bất ngờ khi nhiều nơi tham chiếu tới List gốc.

### 7.2. replaceAll không đồng nghĩa với Collections.replaceAll

~~~java
List<String> values = new ArrayList<>(
        List.of("A", "B", "A")
);

values.replaceAll(s -> s + "!");

// values == [A!, B!, A!]
~~~

Ngược lại:

~~~java
List<String> values = new ArrayList<>(
        List.of("A", "B", "A")
);

boolean changed = java.util.Collections.replaceAll(
        values, "A", "X"
);

// changed == true; values == [X, B, X]
~~~

Hai đoạn trên là **minh họa độc lập**, không đặt cùng scope vì trùng tên biến. **Collections.replaceAll** thay khi phần tử bằng **oldVal** (theo quy tắc so sánh thích hợp); **List.replaceAll** áp dụng một operator lên **mỗi phần tử**, có thể tạo giá trị khác nhau dựa trên từng đầu vào.

### 7.3. replaceAll của List khác Map.replaceAll

**Map.replaceAll((key, value) -> newValue)** nhận **key + value**, cập nhật các **value** trong Map; **List.replaceAll(value -> newValue)** chỉ nhận **giá trị phần tử** và hoạt động theo **vị trí danh sách**. Không tráo chữ ký **UnaryOperator<E>** của List với **BiFunction<K,V,V>** của Map.

Cả hai là các API còn dùng trong Java hiện đại, nhưng khác cấu trúc dữ liệu và ngữ nghĩa.

### 7.4. String.replaceAll không phải List.replaceAll

**"abc".replaceAll(regex, replacement)** là một phương thức trên **String** dùng biểu thức chính quy để tạo chuỗi thay thế, không phải thao tác đổi từng phần tử trong List. Sự trùng tên **replaceAll** không làm các chữ ký hoặc hệ quả của chúng giống nhau.

## 8. Tính đúng đắn khi operator có null

### 8.1. Giá trị đầu vào null

Một List mutable như ArrayList có thể chứa **null**. Nếu dùng method reference hoặc lambda gọi phương thức của phần tử mà không xử lý null, **NullPointerException** có thể xảy ra:

~~~java
// Rủi ro nếu values chứa null:
values.replaceAll(String::trim);
~~~

Đây là đoạn minh họa với **List<String> values** đã được tạo nơi khác. **String::trim** cần một chuỗi thật để gọi phương thức.

Hãy xác lập chính sách nghiệp vụ:

- **Không chấp nhận null:** kiểm tra nguồn trước khi biến đổi và báo lỗi rõ ràng.
- **Cho phép dữ liệu thiếu:** thay bằng một giá trị mặc định có ý nghĩa.
- **Bỏ giá trị null:** đây là thay đổi số phần tử, nên dùng cách phù hợp như **removeIf(Objects::isNull)** nếu List hỗ trợ xóa, hoặc tạo List mới qua filter; **replaceAll** không phải thao tác xóa.

Ví dụ xử lý null bằng giá trị đại diện:

~~~java
List<String> nullable = new ArrayList<>(
        Arrays.asList("A", null, "C")
);

nullable.replaceAll(s ->
        s == null ? "(missing)" : s.toLowerCase(Locale.ROOT)
);

// nullable == [a, (missing), c]
~~~

Đoạn minh họa yêu cầu import **java.util.List**, **ArrayList**, **Arrays**, **Locale**.

### 8.2. Operator trả null

Operator có thể trả **null** nếu List **cho phép phần tử null**:

~~~java
List<Integer> values = new ArrayList<>(
        List.of(1, 2, 3)
);

values.replaceAll(x -> x == 2 ? null : x);

// values == [1, null, 3]
~~~

Nhưng một List có quy tắc cấm null có thể ném **NullPointerException** nếu operator trả null. Đừng giả định rằng **List.replaceAll** luôn cấm null hoặc luôn chấp nhận null; nó phụ thuộc List implementation.

**Operator bản thân là null** cũng không hợp lệ: lời gọi **replaceAll(null)** ném **NullPointerException** theo hợp đồng API.

### 8.3. Giới hạn số trong operator

Ví dụ:

~~~java
scores.replaceAll(n -> n * 1_000_000);
~~~

Dù thao tác list đúng, phép nhân kiểu **int** bên trong có thể tràn nếu giá trị quá lớn. Khi overflow cần được phát hiện, dùng **Math.multiplyExact(...)**; nếu miền dữ liệu có thể vượt kiểu hiện tại, thiết kế phần tử là **Long/BigInteger/BigDecimal** theo yêu cầu thay vì ép kiểu sau khi phép toán đã sai.

**replaceAll không kiểm tra ngữ nghĩa của phép tính hộ bạn.** Nó chỉ gọi operator và lưu kết quả được trả về.

## 9. Nếu operator ném exception: không có rollback mặc định

Một giả định sai là: nếu một lần biến đổi thất bại ở phần tử thứ ba, List sẽ tự quay về trạng thái ban đầu. **List.replaceAll không phải giao dịch nguyên tử (atomic transaction)**.

Lưu thành **ReplaceAllEdgeCasesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ReplaceAllEdgeCasesDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(
                List.of(1, 2, 3, 4)
        );

        try {
            values.replaceAll(x -> {
                if (x == 3) {
                    throw new IllegalArgumentException("bad3");
                }
                return x * 10;
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("partial=" + values);

        List<String> nullable = new ArrayList<>(
                Arrays.asList("A", null, "C")
        );

        nullable.replaceAll(s ->
                s == null
                        ? "(missing)"
                        : s.toLowerCase(Locale.ROOT)
        );

        System.out.println("nullable=" + nullable);

        List<Integer> allowNull = new ArrayList<>(
                List.of(1, 2, 3)
        );

        allowNull.replaceAll(x -> x == 2 ? null : x);
        System.out.println("allowNull=" + allowNull);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReplaceAllEdgeCasesDemo.java
java ReplaceAllEdgeCasesDemo
~~~

**Stdout trên JDK hiện đại cho ArrayList của ví dụ:**

~~~text
error=bad3
partial=[10, 20, 3, 4]
nullable=[a, (missing), c]
allowNull=[1, null, 3]
~~~

**Phân tích:** Trong ví dụ ArrayList này, hai phần tử đầu đã được nhân 10 trước khi operator ném ngoại lệ ở giá trị 3. List còn lại ở trạng thái **biến đổi một phần**. Hợp đồng API nói ngoại lệ do operator ném được chuyển cho người gọi, nhưng **không hứa hoàn nguyên** mọi thay đổi trước đó. Không suy ra mọi List implementation có đúng cùng trạng thái trung gian trong mọi loại lỗi.

### 9.1. Khi nghiệp vụ cần "thành công toàn bộ hoặc không đổi"

Cách đơn giản là **tính kết quả trước trong một List riêng**, chỉ thay dữ liệu gốc sau khi mọi phép biến đổi đã thành công, và kiểm soát thời điểm công bố kết quả. Ví dụ nếu hệ thống cho phép đổi **tham chiếu**:

~~~java
List<Integer> source = new ArrayList<>(
        List.of(1, 2, 3, 4)
);

List<Integer> calculated = source.stream()
        .map(Math::incrementExact)
        .toList();

// Các phép tính đều thành công rồi mới chọn công bố calculated.
// Không phải replaceAll và không thay nội dung source.
~~~

Đây là đoạn minh họa. Cách này **không tự biến việc sửa một shared List thành transaction**: nếu sau đó vẫn gọi **clear/addAll** để chép kết quả vào một List chung, bước cập nhật ấy có thể quan sát được từng phần hoặc tự thất bại. Đối với yêu cầu atomic nghiêm ngặt cần cơ chế synchronization/transaction ở cấp cấu trúc dữ liệu và quyền sở hữu phù hợp.

Nếu người gọi có thể dùng một **tham chiếu List mới** thay vì yêu cầu sửa đúng instance gốc, tính trước rồi **công bố tham chiếu mới** ở ranh giới an toàn thường dễ kiểm soát hơn.

### 9.2. Tránh operator có tác dụng phụ bên ngoài

Không gửi email, ghi database, cập nhật dịch vụ ngoài hoặc tăng bộ đếm global bên trong operator chỉ vì cần đồng thời chuyển đổi phần tử List. Nếu lỗi ở giữa, tác dụng phụ có thể đã xảy ra dù danh sách biến đổi chưa hoàn tất. Tách **tính toán**, **kiểm tra**, **ghi dữ liệu** thành các bước có quy tắc rõ ràng.

## 10. Tác dụng phụ và thay đổi cấu trúc List khi đang replaceAll

**Không sửa cấu trúc cùng một List từ bên trong operator**, ví dụ thêm/xóa phần tử đang được duyệt:

~~~java
// Đoạn minh họa SAI: operator can thiệp vào cùng List.
values.replaceAll(x -> {
    values.add(x + 100);
    return x;
});
~~~

Ví dụ giả sử **values** là List mutable. Hành vi có thể gây **ConcurrentModificationException**, kết quả khó dự đoán hoặc lỗi phụ thuộc triển khai. Fail-fast không phải cơ chế an toàn để dựa vào; cách làm đúng là **không can thiệp vào cấu trúc List đang duyệt**.

Nếu cần thêm/xóa phần tử theo tiêu chí, sử dụng operation khác:

- **removeIf(predicate)** nếu mục tiêu là xóa các phần tử.
- **filter/flatMap** trong Stream rồi tạo List mới nếu muốn số phần tử có thể thay đổi.
- Thu thập phần tử mới vào một List riêng rồi quản lý bước thay thế nguồn theo yêu cầu ứng dụng.

Đừng dùng **replaceAll** như một cách lách để tạo/xóa vị trí: operator chỉ có hợp đồng trả **một E thay thế cho một E hiện tại**.

## 11. Thread-safety và parallel processing

**List.replaceAll không phải một cơ chế song song.** Chữ ký của nó không có tùy chọn **parallel**, không mặc định tách việc trên các thread, và không tự bảo đảm thread-safety cho List. Nếu nhiều thread cùng cập nhật **ArrayList** hoặc đọc List trong lúc một thread replaceAll, cần tổ chức đồng bộ theo hợp đồng của dữ liệu.

Ví dụ cần tránh:

~~~java
// Không dùng List shared mutable trong parallelStream.forEach:
items.parallelStream().forEach(item -> {
    sharedList.add(transform(item));
});
~~~

Đây là ví dụ minh họa phụ thuộc **items**, **sharedList** và **transform(...)** từ ứng dụng. Nếu **sharedList** là ArrayList, nhiều thread gọi add đồng thời không an toàn.

Tương tự, không dùng **parallelStream().forEach(...)** để tự thay từng chỉ số của List dùng chung chỉ vì hy vọng nhanh hơn. Việc ghép side effect với nguồn đang duyệt làm code khó duy trì và có thể vi phạm điều kiện không can thiệp vào nguồn.

Với tác vụ biến đổi không cần in-place, một Stream sử dụng mapper stateless rồi thu thập kết quả mới diễn đạt ý định tốt hơn:

~~~java
List<String> upper = source.parallelStream()
        .map(s -> s.toUpperCase(Locale.ROOT))
        .toList();
~~~

Đoạn minh họa giả sử **source** là List<String> không chứa null và đã import **List**, **Locale**. Cách này không tự bảo đảm nhanh hơn; cần benchmark nếu lý do sử dụng parallel là hiệu năng.

### 11.1. Có nên dùng Collections.synchronizedList?

**Collections.synchronizedList** cung cấp một wrapper cho truy cập đồng bộ theo hợp đồng của nó, nhưng không phải một phép biến đổi atomic across-all-observers khi kết hợp với những thao tác khác mà không giữ khóa đúng cách. Đặc biệt, nếu ứng dụng có nhiều bước đọc/ghi liên quan hoặc thao tác duyệt, cần tuân thủ quy tắc đồng bộ được tài liệu của wrapper quy định.

Không suy ra chỉ cần gọi synchronizedList là mọi nghiệp vụ cập nhật List đều trở thành transaction. Thiết kế xử lý song song nên xem xét mức độ chia sẻ dữ liệu, độ dài critical section và yêu cầu nhất quán.

### 11.2. CopyOnWriteArrayList thì sao?

**CopyOnWriteArrayList** có đặc tính concurrency riêng và hiện thực **replaceAll(...)** theo hợp đồng lớp. Tuy nhiên, đó **không** có nghĩa thao tác trên bất kỳ List nào cũng có cùng mức bảo đảm, chi phí hoặc snapshot semantics. Việc lựa chọn cấu trúc dữ liệu nên dựa vào đặc điểm số lần đọc/ghi và tài liệu của lớp; không đổi mọi ArrayList thành CopyOnWriteArrayList chỉ để dùng replaceAll.

## 12. Hiệu năng, ý nghĩa thiết kế và kiểm thử

Với các List thông thường, **replaceAll** thực hiện một phép biến đổi cho từng phần tử. Thông thường số phần tử là **n**, lượng xử lý tổng thể gần **O(n)** cộng với chi phí operator cho mỗi phần tử. Nhưng không cam kết thời gian tuyệt đối cho mọi List tùy biến hoặc mọi operator (operator có thể rất đắt hoặc ném lỗi).

**Lợi điểm thường thấy:**

- Câu lệnh ngắn gọn, mục đích rõ: cập nhật từng phần tử của **List hiện có**.
- Không phải tự viết vòng lặp chỉ số.
- Không cần tạo một danh sách kết quả mới chỉ để thay phần tử.
- Giữ nguyên thứ tự và số lượng phần tử trong cách dùng bình thường (operator không phá nguồn).
- Có thể dùng lambda, method reference và logic kiểm tra miền dữ liệu.

**Chi phí/rủi ro:**

- Có thể tạo đối tượng mới cho từng phần tử; in-place ở cấp List **không có nghĩa zero allocations**.
- Biến đổi có thể quan sát được qua alias; không phù hợp khi cần List cũ bất biến.
- Có thể thất bại giữa chừng, để lại trạng thái một phần.
- Một số List unmodifiable không hỗ trợ.
- Không tự xử lý race condition, rollback hoặc tính toán song song.
- Nếu operator chứa xử lý I/O/side effect, thời gian và tính đúng đắn phụ thuộc những yếu tố ngoài phép thay List.

### 12.1. Những test nên có

Khi dùng replaceAll trong production, kiểm thử:

1. **List rỗng** và List có một phần tử.
2. Giá trị bình thường, giá trị trùng, chuỗi rỗng, khoảng trắng và ký tự Unicode.
3. Nguồn có **null** hoặc operator trả null, theo chính sách nghiệp vụ.
4. **ArrayList**, **Arrays.asList**, **List.of** và view **subList** nếu ứng dụng chấp nhận nhiều loại List.
5. **ArithmeticException** do phép tính, hoặc ngoại lệ kiểm tra dữ liệu.
6. Đối tượng **mutable** bị chia sẻ qua nhiều tham chiếu.
7. Kết quả khi một bước biến đổi thất bại, đặc biệt nếu nghiệp vụ đòi atomicity.
8. Đồng thời đọc/ghi nếu List thực sự dùng qua nhiều thread.

**Không chỉ kiểm tra list.size()**: replaceAll thường giữ nguyên số phần tử ngay cả khi mọi giá trị đã thay đổi. Kiểm thử phải xem giá trị ở từng vị trí và điều kiện bất biến của danh sách.

### 12.2. Mẫu quyết định nhanh

| Câu hỏi | Nên ưu tiên |
|---|---|
| Cần thay **tất cả phần tử** ngay trong một List mutable? | **list.replaceAll(operator)** |
| Chỉ thay **một vị trí** biết chỉ số? | **list.set(index, value)** |
| Chỉ thay phần tử **bằng một giá trị cũ**? | **Collections.replaceAll(list, old, new)** |
| Cần List kết quả mới, nguồn không đổi? | **stream().map(...).toList()** |
| Cần đổi kiểu **E → R**? | **Stream.map(Function<E,R>)** và thu thập |
| Cần **xóa** phần tử? | **removeIf** hoặc Stream.filter + collect |
| Cần **sắp xếp** vị trí? | **List.sort(comparator)** hoặc Stream.sorted + collect |
| Cần thay một **đoạn** của List có thể sửa? | **subList(from, to).replaceAll(...)** (hiểu backing view) |
| List nguồn không cho thay? | **new ArrayList<>(source)** rồi replaceAll, hoặc tạo List mới qua Stream |
| Cần cập nhật toàn bộ hoặc không cập nhật gì? | Tính/validate riêng và thiết kế bước commit, không phụ thuộc replaceAll |

## 13. Các lỗi thường gặp

**Lỗi 1 — Cho rằng replaceAll trả danh sách mới.**

~~~java
// SAI: replaceAll trả void.
List<String> result = names.replaceAll(String::toUpperCase);
~~~

Cần gọi **names.replaceAll(...)** rồi đọc **names**. Nếu muốn List mới, sử dụng Stream hoặc tạo bản sao mutable trước.

**Lỗi 2 — Gọi trên List.of.**

~~~java
List<String> names = List.of("a", "b");
names.replaceAll(String::toUpperCase); // UnsupportedOperationException
~~~

Dùng **new ArrayList<>(names)** khi có chủ ý sửa bản sao.

**Lỗi 3 — Nghĩ Arrays.asList không cho sửa gì cả.**

~~~java
Integer[] source = {1, 2};
List<Integer> values = Arrays.asList(source);
values.replaceAll(x -> x + 1); // Hợp lệ với danh sách backed by array
~~~

Chỉ các thao tác thay đổi **kích thước** như add/remove mới không được hỗ trợ với list đó. Cần nhớ việc sửa List phản ánh lại vào mảng.

**Lỗi 4 — Dùng operator trả sai kiểu.**

~~~java
// SAI với List<String>:
names.replaceAll(String::length);
~~~

**String::length** trả Integer, không phải String. Muốn đổi kiểu sang Integer, dùng **names.stream().map(String::length).toList()**.

**Lỗi 5 — Không xử lý null.**

~~~java
names.replaceAll(String::trim); // NPE nếu có phần tử null
~~~

Chỉ dùng khi đã xác nhận đầu vào không chứa null hoặc đã có chính sách xử lý dữ liệu thiếu.

**Lỗi 6 — Tạo rủi ro overflow trong lambda.**

~~~java
prices.replaceAll(x -> x * 1_000_000);
~~~

Phép toán với int/long có thể tràn. Dùng hàm Math.*Exact hoặc kiểu số đủ rộng khi yêu cầu tính đúng.

**Lỗi 7 — Nghĩ replaceAll có thể rollback.** Nếu operator ném exception ở phần tử sau, một số phần tử trước có thể đã được thay.

**Lỗi 8 — Dùng mutable object như thể là immutable.** Việc operator cập nhật trực tiếp thuộc tính object có thể gây thay đổi qua alias ngoài List, dù sau đó trả lại cùng object.

**Lỗi 9 — Sửa cấu trúc List bên trong operator.** Có thể phá tính đúng đắn của traversal; không dựa vào cơ chế fail-fast làm lớp bảo vệ.

**Lỗi 10 — Dùng List view mà quên backing list.** **subList.replaceAll** sửa phần tử ở danh sách gốc; cần xác định rõ tác động trước khi gọi.

**Lỗi 11 — Nhầm List.replaceAll với Map.replaceAll hoặc String.replaceAll.** Chữ ký và ngữ nghĩa khác nhau hoàn toàn.

**Lỗi 12 — Đánh đồng "in-place" với "không cấp phát bộ nhớ".** Một operator tạo object hoặc String mới mỗi lần vẫn có thể cấp phát dù **không tạo List kết quả mới**.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** **List.replaceAll(...)** trả gì và có tạo List mới không?

**Câu 2.** Cho **List<Integer> a = new ArrayList<>(List.of(1, 2, 3))**; sau **a.replaceAll(x -> x * 3)**, giá trị a là gì?

**Câu 3.** Nếu **List<String> a = List.of("an", "binh")**, gọi **a.replaceAll(String::toUpperCase)** có hợp lệ khi chạy không? Làm thế nào nếu muốn có bản mới có thể sửa?

**Câu 4.** **Arrays.asList(array)** không hỗ trợ **add**, vậy có hỗ trợ **replaceAll** không? Điều gì xảy ra với mảng nguồn?

**Câu 5.** **list.subList(1, 3).replaceAll(...)** tác động tới List nào?

**Câu 6.** **List<String>** có thể dùng **replaceAll(String::length)** để trở thành **List<Integer>** không?

**Câu 7.** Nếu operator ném exception ở phần tử thứ ba, List có tự rollback về trạng thái ban đầu không?

**Câu 8.** Nếu muốn **giữ nguyên List nguồn**, nên dùng replaceAll hay **stream().map(...).toList()**?

**Câu 9.** Vì sao lambda thay đổi thuộc tính của một đối tượng mutable có thể ảnh hưởng cả bên ngoài List?

**Câu 10.** **Collections.replaceAll(list, old, new)** và **List.replaceAll(operator)** khác gì về mục đích?

**Đáp án:**

1. **Trả void** và **thay các phần tử ngay trong chính List đang gọi**, không tạo List kết quả mới.
2. **[3, 6, 9]**, kích thước vẫn là 3.
3. **Không**; List.of là unmodifiable và ném UnsupportedOperationException. Tạo **new ArrayList<>(a)** trước khi replaceAll, hoặc dùng Stream để lấy List kết quả mới.
4. **Có** với Arrays.asList backed by array; thay phần tử List sẽ cập nhật các vị trí tương ứng trong mảng nguồn.
5. Tác động lên **view subList và backing List gốc** tại các chỉ số trong đoạn [1, 3).
6. **Không**, vì UnaryOperator<String> phải trả String. Dùng Stream.map để biến đổi kiểu.
7. **Không**; một phần trước đó có thể đã được thay. Cần cơ chế tính trước/commit nếu nghiệp vụ đòi atomicity.
8. Dùng **stream().map(...).toList()** với mapper không có side effect.
9. Vì List và phần còn lại của ứng dụng có thể giữ **tham chiếu cùng một object**; sửa state của object sẽ được quan sát qua tất cả tham chiếu đó.
10. **Collections.replaceAll** thay các phần tử khớp **old** bằng **new**; **List.replaceAll** tính lại **mọi phần tử** theo hàm.

## 15. Ghi nhớ và tài liệu tham khảo

- **List.replaceAll(UnaryOperator<E>)** là phép **thay thế phần tử tại chỗ**; cùng một List instance, cùng số vị trí trong cách dùng hợp lệ, **không trả về List**.
- **UnaryOperator<E> nhận E và trả E**; không dùng thay đổi generic element type.
- **ArrayList** và **LinkedList** có thể thay phần tử; **Arrays.asList** có kích thước cố định nhưng thay được; **List.of/List.copyOf** không cho phép replaceAll.
- **subList** là view, nên có thể sửa backing List.
- **Không có rollback tự động** khi operator ném exception. Tránh tác dụng phụ và thao tác thay đổi cấu trúc nguồn trong operator.
- **Stream.map(...).toList()** phù hợp khi muốn List kết quả mới và giữ nguồn không đổi, trong khi **replaceAll** được dùng khi **chủ ý** sửa chính danh sách hiện có.

Tài liệu Oracle Java API hiện hành:

- [List — replaceAll, set, subList và các unmodifiable list (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html)
- [UnaryOperator — Function<E,E> (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/UnaryOperator.html)
- [Arrays.asList — fixed-size list backed by array (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html)
- [ArrayList (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayList.html)
- [Stream — map và toList (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [Collections — replaceAll và các wrapper List (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html)
