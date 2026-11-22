# Spliterator: ORDERED, DISTINCT, SORTED và NONNULL

**Chủ đề:** Java 8 → Spliterator → ORDERED, DISTINCT, SORTED và NONNULL.

**Spliterator<T>** (splitable iterator) là giao diện dùng để **duyệt** và **phân chia** các phần tử từ một nguồn, thường phục vụ Stream API và xử lý song song. Bên cạnh các thao tác **tryAdvance()**, **forEachRemaining()** và **trySplit()**, nó còn công bố tập **characteristics**: những cam kết về cấu trúc, thứ tự và giá trị mà Spliterator sẽ trả ra.

Bốn characteristic trọng tâm của bài:

- **ORDERED:** có thứ tự gặp phần tử (encounter order) được định nghĩa.
- **DISTINCT:** không có hai phần tử được gặp là trùng nhau theo ngữ nghĩa **equals**.
- **SORTED:** phần tử được gặp theo một **thứ tự sắp xếp** xác định; kéo theo **ORDERED**.
- **NONNULL:** mỗi phần tử được cung cấp khi duyệt đều **khác null**.

Các constant **Spliterator.ORDERED**, **Spliterator.DISTINCT**, **Spliterator.SORTED** và **Spliterator.NONNULL** là các cờ bit **int**, không phải bốn phương thức của Stream. Chúng tồn tại từ Java 8 và tiếp tục được hỗ trợ trong Java hiện đại. Ví dụ độc lập bên dưới biên dịch/chạy trên **Java 17+**.

## 1. Spliterator tham gia pipeline như thế nào?

Một **Collection** có thể cung cấp Spliterator qua **collection.spliterator()**. Từ đó, Stream framework có thể duyệt tuần tự hoặc phân chia thành các phần để thực thi song song.

~~~text
Collection / mảng / nguồn dữ liệu
          │
          ▼
     Spliterator<T>
       ├─ characteristics(): biết những cam kết của nguồn
       ├─ tryAdvance(action): lấy một phần tử kế tiếp
       ├─ forEachRemaining(action): duyệt các phần còn lại
       └─ trySplit(): tách một phần việc ra Spliterator khác
          │
          ▼
       Stream pipeline → terminal operation
~~~

**Spliterator không phải bản sao của toàn bộ dữ liệu**. Nó là cơ chế truy cập tới một phần hoặc tất cả phần tử của nguồn. Duyệt hoặc chia Spliterator làm thay đổi vùng phần tử còn lại. Không dùng lại cùng một Spliterator để kỳ vọng bắt đầu từ đầu; mỗi Spliterator dùng cho một lượt duyệt/tính toán.

Các cờ characteristic là **hợp đồng mà Spliterator công bố cho bên sử dụng**, không phải phép kiểm tra dữ liệu tự động từng phần tử. Nếu bạn tự hiện thực Spliterator và công bố một cờ sai, Stream có thể dựa vào cờ đó để tối ưu hóa và cho kết quả sai.

## 2. Bảng ý nghĩa bốn characteristic

| Cờ | Cam kết | Ví dụ minh họa | Không có nghĩa là |
|---|---|---|---|
| **ORDERED** | Có **encounter order** xác định và các phương thức duyệt/split tuân theo thứ tự đó | List theo thứ tự chỉ số | Phần tử đã sắp xếp tăng dần hoặc thao tác parallel **forEach** sẽ in đúng thứ tự |
| **DISTINCT** | Các phần tử được gặp là duy nhất theo **equals** | Set | Có thứ tự, đã sort hoặc không có null |
| **SORTED** | Encounter order tuân theo **Comparator** xác định hoặc thứ tự tự nhiên | SortedSet/TreeSet | Không có giá trị trùng nhau |
| **NONNULL** | Mỗi phần tử được đưa tới action đều khác **null** | Nguồn kiểm soát không phát null | Không có giá trị trùng nhau, có thứ tự hoặc không thể thay đổi nguồn |

**Quan hệ logic chắc chắn:**

~~~text
SORTED ─────► ORDERED

DISTINCT   : độc lập với ORDERED/SORTED/NONNULL
NONNULL    : độc lập với ORDERED/DISTINCT/SORTED
ORDERED    : không kéo theo SORTED
~~~

Vì **SORTED** là thứ tự sắp xếp đã được xác lập, một Spliterator công bố **SORTED** **bắt buộc** cũng phải công bố **ORDERED**. Chiều ngược lại không đúng: một danh sách có thứ tự **[3, 1, 2]** vẫn là ORDERED dù không sorted.

**SORTED không kéo theo DISTINCT:** dãy **[1, 1, 2, 3]** được sắp tăng dần nhưng vẫn có hai phần tử bằng nhau. **DISTINCT không kéo theo SORTED:** một Set có thể không có trùng lặp nhưng không cam kết thứ tự tăng dần. **DISTINCT không kéo theo NONNULL:** một Set có thể chứa **một null** mà vẫn không có phần tử trùng nhau.

## 3. Kiểm tra các cờ bằng API

Hai phương thức phổ biến:

~~~java
int flags = spliterator.characteristics();

boolean ordered =
        spliterator.hasCharacteristics(Spliterator.ORDERED);

boolean both =
        spliterator.hasCharacteristics(
                Spliterator.ORDERED | Spliterator.DISTINCT);
~~~

Đây là **đoạn minh họa**: giả sử biến **spliterator** có kiểu **Spliterator<?>**, đã import **java.util.Spliterator**.

- **characteristics()** trả các characteristic dưới dạng tập bit kết hợp trong một giá trị **int**.
- **hasCharacteristics(mask)** trả **true** nếu **mọi bit được yêu cầu trong mask** đều hiện diện, không phải chỉ cần một cờ.
- Dùng toán tử **|** để kết hợp các cờ. Ví dụ **ORDERED | DISTINCT** yêu cầu **đồng thời** cả ORDERED lẫn DISTINCT.
- Có thể kiểm tra trực tiếp bằng **(flags & Spliterator.ORDERED) != 0**, nhưng **hasCharacteristics(...)** dễ đọc hơn.
- Nếu một cờ **không được công bố**, chỉ biết rằng **không có cam kết tương ứng**. Điều đó **không chứng minh dữ liệu thực tế vi phạm** cờ đó.

Ví dụ: danh sách chỉ chứa hai chuỗi không null chưa chắc công bố **NONNULL**. Spliterator có thể không cam kết cờ này dù các phần tử hiện tại đều hợp lệ.

**Không tự suy ra mask dựa trên việc nhìn vài mẫu dữ liệu**. Đặc biệt, dữ liệu ngẫu nhiên hoặc nguồn có thể thay đổi không thể được chứng minh **DISTINCT** hoặc **NONNULL** chỉ bằng một vài phần tử.

## 4. ORDERED — encounter order và quy tắc tách tiền tố

**ORDERED** khẳng định nguồn có thứ tự gặp phần tử xác định.

Nếu Spliterator báo ORDERED, hợp đồng API yêu cầu:

1. **tryAdvance(action)** duyệt phần tử kế tiếp theo thứ tự.
2. **forEachRemaining(action)** xử lý các phần còn lại theo encounter order trong lượt duyệt tuần tự đó.
3. **trySplit()**, nếu trả về Spliterator khác, phải tách ra một **tiền tố (strict prefix)** của các phần tử còn lại; phần tử ở tiền tố xuất hiện trước phần còn lại theo encounter order.

Ví dụ List:

~~~text
Nguồn:       [10, 20, 30, 40, 50, 60]
ORDERED:      10 → 20 → 30 → 40 → 50 → 60

Một cách split hợp lệ:
tiền tố:     [10, 20, 30]
phần còn lại:            [40, 50, 60]
~~~

**trySplit() không hứa luôn chia chính xác một nửa**, cũng không hứa luôn trả non-null. Nó có thể từ chối chia vì nguồn, kích thước, thời điểm duyệt hoặc chiến lược triển khai. **ORDERED** chỉ áp đặt quy tắc thứ tự khi thao tác chia xảy ra.

### 4.1. ORDERED không có nghĩa là đã sắp xếp

~~~java
List<Integer> values = List.of(3, 1, 2);
Spliterator<Integer> s = values.spliterator();

// s có ORDERED vì List có thứ tự theo chỉ số.
// Không có căn cứ để suy ra s có SORTED.
~~~

Dãy **[3, 1, 2]** có thứ tự vị trí rõ ràng nhưng không tăng dần.

**ORDERED cũng không có nghĩa tất cả action trong parallel Stream.forEach() được gọi tuần tự theo thứ tự**. Một pipeline song song có thể xử lý phần tử ở các thread và thời điểm khác nhau. Khi cần action theo encounter order, dùng **forEachOrdered(...)**; khi cần danh sách theo encounter order, dùng terminal operation có hợp đồng giữ thứ tự như **toList()** với nguồn ordered.

~~~java
// Đoạn minh họa có nguồn List ordered.
List<Integer> result = values.parallelStream()
        .map(x -> x * 10)
        .toList();
// result == [30, 10, 20]
~~~

**map()** không tự sort. Kết quả giữ thứ tự logic của nguồn List, không phản ánh thread nào xử lý xong trước.

### 4.2. Ví dụ hoàn chỉnh: trySplit với ORDERED

Lưu thành **OrderedSplitDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class OrderedSplitDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(10, 20, 30, 40, 50, 60);
        Spliterator<Integer> remaining = values.spliterator();

        Spliterator<Integer> prefix = remaining.trySplit();
        List<Integer> merged = new ArrayList<>();

        if (prefix != null) {
            prefix.forEachRemaining(merged::add);
        }
        remaining.forEachRemaining(merged::add);

        System.out.println("ordered="
                + values.spliterator()
                        .hasCharacteristics(Spliterator.ORDERED));
        System.out.println("reconstructed=" + merged.equals(values));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderedSplitDemo.java
java OrderedSplitDemo
~~~

**Stdout:**

~~~text
ordered=true
reconstructed=true
~~~

**Giải thích:** Nếu **trySplit()** thành công, Spliterator được trả về quản lý tiền tố, còn **remaining** quản lý phần còn lại. Duyệt **prefix trước remaining** khôi phục thứ tự gốc. Nếu không thể split, chỉ duyệt remaining vẫn cho cùng danh sách. Ví dụ **không phụ thuộc kích thước hai phần**.

Ở chế độ parallel thực tế, các phần có thể được xử lý cùng lúc, sau đó Stream framework phải giữ những ràng buộc về thứ tự mà terminal operation yêu cầu.

## 5. DISTINCT — sự duy nhất theo equals

**DISTINCT** khẳng định các phần tử được Spliterator trả ra **khác nhau theo tiêu chí bình đẳng của Object.equals(...)**. Đối với một tập hợp biểu diễn các giá trị duy nhất, đặc tính này có thể giúp Stream tránh một số thao tác khử trùng lặp không cần thiết.

~~~text
[3, 1, 2]  có thể DISTINCT, dù không SORTED.
[1, 1, 2]  không DISTINCT, dù được sắp tăng dần.
~~~

**Đừng nhầm DISTINCT với số lần xuất hiện được quan sát trong một lượt chạy.** Cờ này là một **cam kết cho toàn bộ phạm vi phần tử**. Nếu Spliterator được khai báo DISTINCT nhưng trả hai phần tử bằng nhau, nó vi phạm hợp đồng.

### 5.1. Set và DISTINCT

**Set** được thiết kế để chứa các phần tử không trùng nhau. Các Spliterator của Set có thể công bố **DISTINCT**, nhưng **Set không nhất thiết công bố ORDERED hoặc SORTED**:

- **HashSet:** không cam kết encounter order cụ thể; không nên viết code đòi "phần tử đầu tiên" cố định.
- **LinkedHashSet:** duy trì thứ tự duyệt được định nghĩa (thường là thứ tự chèn với constructor thông dụng); có thể có **ORDERED + DISTINCT**.
- **TreeSet:** có thứ tự sắp xếp theo comparator hoặc thứ tự tự nhiên; một Spliterator của SortedSet công bố **ORDERED + SORTED + DISTINCT** theo hợp đồng SortedSet.

Lưu ý về **TreeSet và Comparator**: SortedSet quyết định tính trùng nhau theo phép so sánh; để tuân thủ hợp đồng của Set dựa trên **equals**, comparator nên **consistent with equals**. Nếu comparator coi hai phần tử khác nhau theo equals là bằng nhau (hoặc ngược lại), ứng dụng có thể thấy hành vi khó hiểu. Không dùng comparator không nhất quán rồi cho rằng mọi giả định về bình đẳng của bài toán vẫn đúng.

### 5.2. DISTINCT không đòi NONNULL

Một **HashSet<String>** có thể chứa đúng một phần tử **null** cùng các chuỗi khác nhau mà vẫn là một tập không trùng lặp. Vì thế không suy ra **NONNULL** từ **DISTINCT**.

~~~java
// Đoạn minh họa có import java.util.*:
Set<String> values = new HashSet<>();
values.add("A");
values.add(null);

boolean containsNull = values.contains(null); // true
boolean distinct =
        values.spliterator().hasCharacteristics(
                Spliterator.DISTINCT); // true
~~~

**Giá trị null không tự động làm một tập mất tính duy nhất.** Nhưng nếu một bước sau của pipeline gọi phương thức trên từng phần tử như **String::length**, cần có chính sách xử lý null rõ ràng.

### 5.3. DISTINCT và Stream.distinct() là hai khái niệm liên quan

- **Spliterator.DISTINCT**: cờ mô tả đặc điểm của nguồn/Spliterator.
- **Stream.distinct()**: intermediate operation tạo stream chứa các phần tử duy nhất theo **equals**.

~~~java
List<Integer> input = List.of(3, 1, 3, 2, 1);

List<Integer> unique = input.stream()
        .distinct()
        .toList();

// unique == [3, 1, 2] với nguồn List ordered
~~~

Đoạn trên cần import **java.util.List**, sử dụng Java 17+. **distinct()** ở stream ordered giữ phần tử xuất hiện đầu tiên cho mỗi nhóm trùng lặp, nhưng **không tự sắp xếp**. Ở stream unordered, thao tác không cam kết chọn phần tử đại diện đầu tiên theo thứ tự nguồn.

Nếu Spliterator **công bố DISTINCT sai** trong khi vẫn trả phần tử trùng nhau, một pipeline như **distinct()** có thể tận dụng cờ nguồn và bỏ việc khử trùng lặp, dẫn đến kết quả sai. **Độ trung thực của characteristic là yếu tố ảnh hưởng tính đúng đắn**, không chỉ hiệu năng.

## 6. SORTED — thứ tự sắp xếp và Comparator

**SORTED** mạnh hơn ORDERED: ngoài việc có encounter order, Spliterator còn cam kết phần tử đã được sắp theo một **sort order** xác định.

Theo Java API:

- **SORTED bắt buộc kéo theo ORDERED.**
- Nếu sort order là **thứ tự tự nhiên**, **getComparator() trả null**.
- Nếu sort order đến từ một **Comparator**, **getComparator() trả comparator đó**.
- Nếu Spliterator **không công bố SORTED**, lời gọi **getComparator()** phải ném **IllegalStateException**.

### 6.1. SORTED không đồng nghĩa với DISTINCT

~~~text
[1, 1, 2, 2, 3]    : SORTED có thể đúng, DISTINCT sai.
[2, 1, 3]          : DISTINCT có thể đúng, SORTED sai.
[1, 2, 3]          : có thể cả SORTED và DISTINCT.
~~~

Sắp xếp là về **thứ tự**, khử trùng lặp là về **bình đẳng**. Nếu cần cả hai, hãy xác lập cả hai quy tắc.

### 6.2. getComparator() và giá trị null

Một sai lầm phổ biến: thấy **getComparator() == null** rồi kết luận "nguồn không có comparator, vậy không sorted". Điều đó sai với Spliterator đã công bố **SORTED**: **null** trong trường hợp này có nghĩa là **sorted theo natural ordering**, không phải thiếu thông tin.

~~~java
// Đoạn minh họa có import java.util.*:
TreeSet<Integer> natural = new TreeSet<>(List.of(3, 1, 2));
Spliterator<Integer> s = natural.spliterator();

boolean sorted = s.hasCharacteristics(Spliterator.SORTED); // true
boolean naturalOrder = s.getComparator() == null;           // true
~~~

Với kiểu **Integer**, natural ordering là thứ tự tăng dần.

Nếu muốn sort giảm dần, cần comparator phù hợp:

~~~java
TreeSet<Integer> reverse =
        new TreeSet<>(Comparator.reverseOrder());
reverse.addAll(List.of(3, 1, 2));

Spliterator<Integer> s = reverse.spliterator();
Comparator<? super Integer> cmp = s.getComparator();

// cmp khác null; cmp.compare(3, 2) < 0 là true
~~~

Đoạn này minh họa cách đọc comparator. **Không được dùng s.getComparator() nếu s không công bố SORTED**. Trạng thái của tập hợp sorted không thay đổi vì gọi getComparator.

### 6.3. SORTED của Spliterator khác tên hàm Stream.sorted()

**Stream.sorted()** là thao tác trung gian sắp xếp phần tử trong pipeline. **Spliterator.SORTED** là một characteristic của Spliterator đang xét. Chúng liên quan nhưng không đồng nghĩa với lời cam kết rằng *mọi* implementation Stream sẽ công bố đúng cùng một bit sau mọi cách gọi **sorted(...)**.

Điều cần dựa vào:

- **stream.sorted()** cho kết quả sorted theo natural order của phần tử, nếu các phần tử có thể so sánh.
- **stream.sorted(comparator)** cho kết quả theo comparator được chỉ định.
- Chỉ gọi **spliterator.getComparator()** khi **spliterator.hasCharacteristics(SORTED)** trả true; không giả định cờ chỉ từ tên phép biến đổi trước đó.
- **sorted() không xóa bản sao bằng nhau**, và **distinct() không tự sort**.

Nếu xây dựng Spliterator tùy biến, trách nhiệm đảm bảo **SORTED/ORDERED/getComparator** thuộc về implementation của bạn, không phải do một phương thức **Stream.sorted()** ở chỗ khác tự sửa nó.

## 7. NONNULL — bảo đảm phần tử không null

**NONNULL** xác nhận **không phần tử nào được giao cho action khi duyệt là null**.

~~~java
// Ví dụ giả định Spliterator công bố NONNULL:
boolean nonNull = spliterator.hasCharacteristics(
        Spliterator.NONNULL);
~~~

Nếu **nonNull == true**, bên tiêu thụ được quyền dựa vào cam kết đó. Nếu **false**, điều đó **chỉ là thiếu cam kết**: dữ liệu thực tế có thể vẫn toàn các phần tử khác null.

Ví dụ **List.of("An", "Binh")** không chấp nhận null ngay khi tạo danh sách. Tuy vậy, **không được tự suy rằng mọi Spliterator trả từ mọi danh sách không có null đều công bố bit NONNULL**. Hãy đọc cờ thực tế nếu thuật toán phụ thuộc nó.

### 7.1. NONNULL và DISTINCT độc lập

- **NONNULL** không cấm hai chuỗi **"A"** giống hệt nhau.
- **DISTINCT** không cấm **một phần tử null** trong một nguồn có tính duy nhất.
- **ORDERED** không chứng minh dữ liệu không null.
- **SORTED** không thay thế chính sách null của comparator hoặc nguồn dữ liệu.

Nếu cần loại null khỏi stream:

~~~java
// Đoạn minh họa có import java.util.* và List<String> words:
List<String> cleaned = words.stream()
        .filter(Objects::nonNull)
        .toList();
~~~

Về mặt **kết quả**, cleaned sẽ không chứa null. Tuy nhiên, **việc dùng filter(Objects::nonNull)** không có nghĩa bạn được tùy ý khẳng định một Spliterator bất kỳ sau đó luôn công bố **NONNULL**; hãy phân biệt tính chất **ngữ nghĩa dữ liệu** với **bit characteristic do implementation báo cáo**.

### 7.2. NONNULL không được kiểm tra tự động khi công bố

Có thể dùng factory **Spliterators.spliterator(array, additionalCharacteristics)** để tạo Spliterator cho một mảng và công bố thêm những cờ mà **bạn thật sự bảo đảm**:

~~~java
String[] names = {"An", "Binh", "Chi"};
Spliterator<String> s = Spliterators.spliterator(
        names,
        Spliterator.ORDERED | Spliterator.NONNULL
);
~~~

Đây là đoạn minh họa; cần import **java.util.Spliterator** và **java.util.Spliterators**. Do dữ liệu cố định không có null và được duyệt theo thứ tự chỉ số, hai cờ được chỉ định là trung thực. Factory còn công bố một số characteristic về kích thước theo đặc tả.

Nếu thay một phần tử mảng thành **null** nhưng vẫn công bố **NONNULL**, bạn đã **nói sai với bên tiêu thụ**. Factory không tự quét toàn bộ mảng để xác minh lời hứa. Tránh thay đổi mảng sau khi Spliterator đã được dùng; nếu cần snapshot bất biến, sao chép dữ liệu hoặc chọn nguồn phù hợp trước khi công bố characteristic.

**Không tự thêm SORTED hoặc DISTINCT** vào mask khi mảng không thỏa các điều kiện, hoặc khi không đáp ứng yêu cầu bổ sung như **getComparator()** đối với SORTED.

## 8. Ví dụ hoàn chỉnh: kiểm tra các cờ trên nguồn thường gặp

Lưu thành **SpliteratorFlagsDemo.java**:

~~~java
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.TreeSet;

public class SpliteratorFlagsDemo {
    public static void main(String[] args) {
        Spliterator<Integer> list =
                List.of(3, 1, 2, 2).spliterator();

        System.out.println("list ORDERED="
                + list.hasCharacteristics(Spliterator.ORDERED));

        Spliterator<Integer> linked =
                new LinkedHashSet<>(List.of(3, 1, 2)).spliterator();

        System.out.println("linked ORDERED+DISTINCT="
                + linked.hasCharacteristics(
                        Spliterator.ORDERED | Spliterator.DISTINCT));

        Spliterator<Integer> tree =
                new TreeSet<>(List.of(3, 1, 2)).spliterator();

        System.out.println("tree SORTED+ORDERED="
                + tree.hasCharacteristics(
                        Spliterator.SORTED | Spliterator.ORDERED));

        System.out.println("tree natural="
                + (tree.getComparator() == null));

        TreeSet<Integer> reverse =
                new TreeSet<>(Comparator.reverseOrder());
        reverse.addAll(List.of(3, 1, 2));

        Spliterator<Integer> reverseSpliterator =
                reverse.spliterator();

        System.out.println("reverse comparator="
                + (reverseSpliterator.getComparator().compare(3, 2) < 0));

        Spliterator<String> explicit = Spliterators.spliterator(
                new String[] {"An", "Binh"},
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        System.out.println("explicit ORDERED+NONNULL="
                + explicit.hasCharacteristics(
                        Spliterator.ORDERED | Spliterator.NONNULL));

        Spliterator<Integer> notSorted = Spliterators.spliterator(
                new Integer[] {2, 1},
                Spliterator.ORDERED
        );

        try {
            notSorted.getComparator();
        } catch (IllegalStateException exception) {
            System.out.println(
                    "unsorted getComparator=IllegalStateException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SpliteratorFlagsDemo.java
java SpliteratorFlagsDemo
~~~

**Stdout:**

~~~text
list ORDERED=true
linked ORDERED+DISTINCT=true
tree SORTED+ORDERED=true
tree natural=true
reverse comparator=true
explicit ORDERED+NONNULL=true
unsorted getComparator=IllegalStateException
~~~

Các dòng đầu kiểm tra **những bảo đảm phù hợp với từng nguồn**, không in ra toàn bộ bitmask và không dựa vào cờ không được hứa trong hợp đồng. **List** duyệt theo thứ tự chỉ số; **LinkedHashSet** giữ thứ tự và tính duy nhất; **TreeSet** công bố sắp xếp theo thứ tự tự nhiên hoặc comparator riêng.

Lời gọi **hasCharacteristics(ORDERED | DISTINCT)** là phép kiểm tra **cả hai bit cùng hiện diện**. **TreeSet.getComparator() == null** có nghĩa là **thứ tự tự nhiên**, trong khi một Spliterator không công bố SORTED sẽ ném **IllegalStateException** khi gọi getComparator.

Ví dụ được kiểm thử trên một JDK hiện đại; cú pháp dùng được trên Java 17+.

## 9. Tương tác với Stream: flags là thông tin nguồn, operations là phép biến đổi

Một nguồn có đặc tính nhất định có thể giúp Stream tối ưu pipeline, nhưng **đừng đồng nhất cờ của Spliterator nguồn với mọi thuộc tính của từng stage trong Stream**.

### 9.1. ORDERED và các terminal operation

~~~java
List<Integer> values = List.of(4, 2, 3, 1);

List<Integer> result = values.parallelStream()
        .map(x -> x * 2)
        .toList();

// result == [8, 4, 6, 2]
~~~

Đây là đoạn minh họa. **toList()** giữ encounter order của stream khi nguồn ordered, cho dù quá trình tính map có thể chia thành nhiều nhánh.

Trái lại:

~~~java
// Thứ tự gọi println không được bảo đảm trên parallel stream:
values.parallelStream().forEach(System.out::println);
~~~

**forEach(...)** không nhất thiết tuân theo encounter order. Nếu cần tác dụng phụ theo thứ tự, dùng **forEachOrdered(...)**. Với nguồn không có encounter order, **forEachOrdered** cũng không tự tạo một thứ tự nghiệp vụ có ý nghĩa.

### 9.2. DISTINCT và distinct()

~~~java
List<Integer> values = List.of(3, 1, 3, 2);
List<Integer> unique = values.stream()
        .distinct()
        .toList();
// unique == [3, 1, 2]
~~~

Khi nguồn là Set đã công bố DISTINCT, **distinct()** có thể có ít công việc hơn; khi nguồn là List chứa trùng, Stream cần khử trùng lặp thực sự. Nhưng **không thể dùng DISTINCT để kết luận kết quả đã sorted**.

### 9.3. SORTED và sorted()

~~~java
List<Integer> values = List.of(3, 1, 2, 2);

List<Integer> sorted = values.stream()
        .sorted()
        .toList();
// sorted == [1, 2, 2, 3]

List<Integer> uniqueSorted = values.stream()
        .distinct()
        .sorted()
        .toList();
// uniqueSorted == [1, 2, 3]
~~~

**sorted()** không làm mất số 2 trùng; **distinct()** không tự sắp tăng dần. Hai kết quả thể hiện hai yêu cầu khác nhau.

Nếu dùng comparator riêng, kết quả **sorted(comparator)** tuân theo comparator, nhưng **không dựa vào việc một Spliterator trung gian phải công bố bit SORTED trong mọi trường hợp và mọi implementation**. Bảo đảm quan trọng là **ngữ nghĩa của terminal result**, không phải phỏng đoán các cờ nội bộ.

### 9.4. NONNULL và null pipeline

Nếu nguồn **NONNULL**, một thao tác **map(...)** có thể tạo null từ phần tử ban đầu, ví dụ:

~~~java
List<String> names = List.of("An", "Binh");

List<String> results = names.stream()
        .map(name -> name.equals("An") ? null : name)
        .toList();

// results == [null, "Binh"]
~~~

**Đoạn này minh họa Java 17+**; **Stream.toList()** cho phép phần tử null, trong khi **List.of(...)** và **List.copyOf(...)** không chấp nhận null. **NONNULL của nguồn không tự lan truyền qua phép map bất kỳ**, vì mapper có thể tạo null.

Nếu cần dữ liệu không null để gọi **String::length**, hãy thiết kế mapper trả non-null hoặc có bước lọc/validate theo nghiệp vụ.

## 10. Tạo Spliterator trung thực từ mảng và StreamSupport

Đôi khi bạn có một nguồn dữ liệu tùy chỉnh, muốn đưa vào Stream bằng **StreamSupport.stream(spliterator, parallel)**. Ví dụ dùng factory cho mảng có thứ tự và không null:

Lưu thành **SpliteratorSourceDemo.java**:

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class SpliteratorSourceDemo {
    public static void main(String[] args) {
        String[] names = {"An", "Binh", "Chi"};

        Spliterator<String> s = Spliterators.spliterator(
                names,
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        List<String> upper = StreamSupport.stream(s, false)
                .map(String::toUpperCase)
                .toList();

        System.out.println("upper=" + upper);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SpliteratorSourceDemo.java
java SpliteratorSourceDemo
~~~

**Stdout:**

~~~text
upper=[AN, BINH, CHI]
~~~

**Giải thích:** **StreamSupport.stream(s, false)** tạo stream tuần tự từ Spliterator này. Đối số thứ hai là **boolean parallel**: **false** yêu cầu stream tuần tự, **true** yêu cầu stream song song. Nó **không thêm ORDERED hoặc NONNULL**, mà dùng những cam kết đã có của Spliterator đầu vào.

Nguồn mảng được thiết kế không thay đổi trong khi duyệt, nên các characteristic khai báo có ý nghĩa. Nếu mảng có thể bị thread khác sửa cùng lúc, **ORDERED/NONNULL** tự chúng không đảm bảo an toàn đồng thời hay nhất quán snapshot.

**Một Spliterator đã được tiêu thụ qua Stream là dùng xong**. Muốn xử lý lại, hãy tạo Spliterator/Stream mới từ nguồn thay vì đưa cùng đối tượng s vào terminal operation thứ hai.

## 11. Những lỗi cần tránh khi tự triển khai Spliterator

### Lỗi 1 — khai SORTED nhưng không khai ORDERED

~~~java
// SAI về hợp đồng: SORTED bắt buộc phải đi với ORDERED.
int wrongFlags = Spliterator.SORTED;
~~~

Đây là **đoạn minh họa mask không hợp lệ** đối với Spliterator tự triển khai, không phải một chương trình đầy đủ. Nếu tự viết **characteristics()**, cần tuân theo quan hệ SORTED ⇒ ORDERED.

### Lỗi 2 — SORTED nhưng getComparator() không tuân hợp đồng

Khi tự tạo Spliterator báo **SORTED**, bạn phải bảo đảm **getComparator()** cung cấp comparator thích hợp hoặc **null nếu thứ tự tự nhiên**. Không được cứ công bố SORTED rồi để getComparator hoạt động như một Spliterator không sorted.

### Lỗi 3 — khai DISTINCT chỉ vì thấy vài phần tử không trùng

~~~text
Dữ liệu xem thử: A, B, C
Dữ liệu toàn bộ: A, B, C, A
~~~

Quan sát tiền tố không đủ để chứng minh DISTINCT cho toàn nguồn. Một characteristic sai có thể khiến **Stream.distinct()** tối ưu sai.

### Lỗi 4 — khai NONNULL rồi thực tế phát null

~~~java
// SAI nếu dữ liệu đầu vào còn null:
String[] values = {"A", null};
Spliterator<String> wrong = Spliterators.spliterator(
        values, Spliterator.NONNULL);
~~~

Factory nhận bitmask theo tuyên bố của người gọi; nó không chứng minh mọi giá trị đầu vào hợp lệ. Cách đúng là **validate dữ liệu** trước, thay nguồn/transform theo chính sách rõ ràng, rồi mới công bố cam kết.

### Lỗi 5 — nhầm ORDERED với sorted

**List.of(3, 1, 2)** là ordered theo vị trí, không sorted. Nếu cần tăng dần, thực hiện **sorted()**, hoặc chọn cấu trúc dữ liệu sorted và hợp đồng tương ứng.

### Lỗi 6 — nhầm DISTINCT với không có null

Một Set có thể có một null mà vẫn duy nhất. Nếu code đòi mọi phần tử khác null, phải kiểm tra **NONNULL** hoặc validate dữ liệu thực sự.

### Lỗi 7 — dùng getComparator() không kiểm tra SORTED

~~~java
// Chỉ minh họa; s phải có kiểu Spliterator<T>.
if (s.hasCharacteristics(Spliterator.SORTED)) {
    var comparator = s.getComparator(); // có thể null = natural
}
~~~

Cần hiểu rằng **null là tín hiệu thứ tự tự nhiên** khi SORTED, không phải một Comparator object để gọi **compare(...)**. Nếu không SORTED, **getComparator()** ném **IllegalStateException**.

### Lỗi 8 — split sai tiền tố

Với ORDERED, **trySplit()** phải trả một **strict prefix** của các phần tử còn lại, không phải một tập con tùy ý hoặc các phần tử lấy xen kẽ nếu như thế phá thứ tự tiền tố. Các Spliterator sau split cũng phải báo cáo characteristic đúng cho phần dữ liệu chúng thực sự quản lý.

### Lỗi 9 — dùng cùng Spliterator đồng thời ở hai thread

**Bốn cờ ORDERED/DISTINCT/SORTED/NONNULL không làm Spliterator thread-safe**. Theo đặc tả, Spliterator nói chung không được thiết kế cho nhiều thread thao tác đồng thời trên **cùng instance**. Cách dùng song song đúng là **chia rồi bàn giao các Spliterator riêng cho các nhánh**. Các cờ khác như **CONCURRENT/IMMUTABLE** có ý nghĩa riêng về khả năng thay đổi nguồn, không thay thế việc tổ chức quyền truy cập đúng.

### Lỗi 10 — kiểm tra mask trước khi thiết kế ngữ nghĩa

Không tự thêm cờ vào source chỉ vì mong muốn tối ưu. **Characteristic là hợp đồng về nguồn**, không phải chỉ thị yêu cầu Stream "hãy làm dữ liệu trở nên DISTINCT/SORTED/NONNULL". Nếu cần thay đổi dữ liệu, dùng **distinct/sorted/filter**, hoặc chọn dữ liệu nguồn bảo đảm yêu cầu từ đầu.

## 12. Kiểm thử những cam kết được công bố

Khi viết Spliterator tùy biến, nên kiểm tra cả API flag lẫn dữ liệu đầu ra. Một chiến lược:

| Nếu công bố | Kiểm thử cần làm |
|---|---|
| **ORDERED** | Duyệt bằng tryAdvance/forEachRemaining đúng encounter order; sau trySplit, phần được trả là tiền tố |
| **DISTINCT** | Không tồn tại hai phần tử bằng nhau theo equals trong tập được duyệt; xem cả dữ liệu biên |
| **SORTED** | Có ORDERED; duyệt không vi phạm comparator/natural ordering; getComparator đúng hành vi |
| **NONNULL** | Không phần tử nào được chuyển cho action là null, cả sau khi chia và duyệt |
| **Nhiều cờ** | Tất cả các điều kiện đều đúng đồng thời, không chỉ một số cờ |
| **Parallel source** | Các nhánh split không mất/lặp phần tử; không dùng cùng instance đồng thời; không thay nguồn không an toàn |

### 12.1. Phép kiểm tra theo đặc tính không thay thế kiểm tra nội dung

Ví dụ:

~~~java
boolean expected = spliterator.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.NONNULL);
~~~

Đây là đoạn minh họa. **expected == true** chỉ xác nhận Spliterator đã **công bố** hai bit. Nó không thực hiện quét dữ liệu để chứng minh không có null. Nếu Spliterator là implementation do bạn viết, cần có unit test và bảo đảm logic tạo nguồn tương ứng.

### 12.2. Không cố định những flag không được bảo đảm bởi API

Trong các JVM khác nhau, một số implementation có thể công bố thêm hoặc ít hơn các characteristic không bắt buộc. Ví dụ một nguồn không chứa null trên thực tế không nhất thiết báo **NONNULL**. Khi viết test thư viện hay dạy API, ưu tiên **những cờ được tài liệu lớp nguồn cam kết** thay vì hard-code toàn bộ số nguyên từ **characteristics()** cho một phiên bản JDK.

### 12.3. Kiểm tra với nguồn thay đổi và với phần sau trySplit

Nếu dùng một Collection mutable, thay đổi cấu trúc nguồn giữa lúc Spliterator gắn với nguồn và hoàn tất duyệt có thể vi phạm điều kiện của implementation, gây **ConcurrentModificationException** hoặc hành vi không xác định theo hợp đồng. **ORDERED/DISTINCT/SORTED/NONNULL không cho phép bỏ qua các quy tắc can thiệp vào nguồn**.

Đối với Spliterator tùy biến, hãy kiểm thử các trường hợp nguồn rỗng, một phần tử, nhiều phần tử, chia ở những vị trí khác nhau, comparator riêng, giá trị trùng, giá trị null (nếu được hỗ trợ) và khi xuất hiện thay đổi nguồn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Dãy **[3, 1, 2]** được duyệt đúng theo thứ tự chỉ số của List. Nó có ORDERED hay SORTED?

**Câu 2.** Một nguồn cung cấp **[1, 1, 2]** theo thứ tự tăng dần. Có thể công bố **SORTED** và **DISTINCT** cùng lúc không?

**Câu 3.** **SORTED** bắt buộc kéo theo characteristic nào?

**Câu 4.** Khi **s.hasCharacteristics(SORTED)** là true, **s.getComparator() == null** có nghĩa gì?

**Câu 5.** Vì sao không được gọi **getComparator()** trên Spliterator không công bố SORTED?

**Câu 6.** Một **HashSet** có đúng một phần tử null cùng vài phần tử khác. Việc đó tự làm mất **DISTINCT** hay không? Có được suy ra **NONNULL** không?

**Câu 7.** Với **hasCharacteristics(ORDERED | DISTINCT)**, giá trị true có nghĩa gì?

**Câu 8.** Nếu Spliterator công bố **ORDERED**, trySplit() có được trả các phần tử ở vị trí 0, 2, 4 trong khi phần còn lại giữ 1, 3, 5 không?

**Câu 9.** Sau **Stream.sorted()**, có được khẳng định các giá trị trùng nhau bị xóa không?

**Câu 10.** Khi tự dùng factory tạo Spliterator với **NONNULL**, ai chịu trách nhiệm đảm bảo nguồn thực tế không chứa null?

**Đáp án:**

1. **ORDERED**; không thể suy ra **SORTED** vì thứ tự List không phải thứ tự tăng dần.
2. Có thể **SORTED**, nhưng **không DISTINCT** vì số 1 xuất hiện hai lần.
3. **ORDERED**.
4. Các phần tử sorted theo **thứ tự tự nhiên**.
5. Theo hợp đồng, **getComparator()** trên Spliterator không SORTED ném **IllegalStateException**.
6. **DISTINCT có thể vẫn đúng**; không được suy ra NONNULL khi nguồn có null.
7. **Cả hai cờ đều có mặt**, không phải chỉ một.
8. **Không**; nếu split thành công thì Spliterator được trả phải quản lý một **strict prefix** của các phần tử còn lại.
9. **Không**; **sorted()** tạo thứ tự, còn **distinct()** mới loại trùng.
10. **Người viết/đưa dữ liệu vào Spliterator**; factory nhận các đặc tính đã khai báo chứ không tự xác thực mọi giá trị.

## 14. Tổng kết

Bốn characteristic giải quyết **bốn câu hỏi khác nhau** về dữ liệu đi qua Spliterator:

- **ORDERED:** có thứ tự gặp phần tử mà việc duyệt và chia phải tôn trọng không?
- **DISTINCT:** có bảo đảm các phần tử duy nhất theo equals không?
- **SORTED:** thứ tự gặp phần tử có tuân theo sort order xác định không?
- **NONNULL:** có bảo đảm mọi phần tử đều khác null không?

Chỉ có quan hệ bắt buộc đáng ghi nhớ trong nhóm này là **SORTED ⇒ ORDERED**. Những liên hệ khác phải được chứng minh từ nguồn/implementation cụ thể; không suy luận từ tên collection hoặc dữ liệu mẫu một cách tùy tiện. Khi tự xây Spliterator, hãy **công bố trung thực các characteristic và tuân thủ getComparator/trySplit**, bởi Stream có thể dựa vào chúng để tối ưu.

### Tài liệu chính thức, còn áp dụng

- [Spliterator — đặc tả ORDERED, DISTINCT, SORTED, NONNULL, getComparator, trySplit (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html)
- [SortedSet — Spliterator và comparator (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/SortedSet.html)
- [Spliterators — các factory phương thức tạo Spliterator (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterators.html)
- [Stream — sorted(), distinct(), forEach(), toList() (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [java.util.stream — Ordering và Parallelism (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
