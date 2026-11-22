# Phân biệt loại phần tử trùng với giữ tất cả phần tử rồi sắp xếp

Khi làm việc với dữ liệu Java, **sắp xếp** và **loại phần tử trùng** là hai thao tác khác nhau. Sắp xếp chỉ thay đổi thứ tự các phần tử theo một quy tắc; loại trùng làm giảm số phần tử bằng cách giữ một đại diện cho mỗi nhóm được coi là tương đương. Một `TreeSet` thực hiện cả hai hành vi: duy trì thứ tự và chỉ giữ **một phần tử trong mỗi nhóm có kết quả so sánh bằng `0`**. Ngược lại, `List.sort(...)` hoặc `Stream.sorted(...)` sắp xếp nhưng **giữ nguyên các lần xuất hiện**, kể cả giá trị lặp.

Đây là khác biệt quan trọng trong chủ đề **tập hợp có thứ tự** và hợp đồng đối tượng: việc quyết định hai phần tử “trùng” trong `TreeSet` dựa trên **`compareTo` hoặc `Comparator.compare`**, không nhất thiết trùng với `equals`.

## 1. Hai yêu cầu khác nhau dẫn tới hai kết quả khác nhau

Giả sử dữ liệu đầu vào là:

```text
[pear, apple, pear, banana, apple]
```

Ta có thể muốn:

| Yêu cầu | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Giữ nguyên dữ liệu | `[pear, apple, pear, banana, apple]` | Thứ tự nhập và số lần xuất hiện không đổi |
| **Chỉ sắp xếp** tăng dần | `[apple, apple, banana, pear, pear]` | Giữ đủ 5 phần tử, chỉ đổi vị trí |
| **Loại trùng rồi sắp xếp** | `[apple, banana, pear]` | Còn 3 giá trị khác nhau |
| **Đếm số lần xuất hiện theo thứ tự khóa** | `{apple=2, banana=1, pear=2}` | Giữ thông tin tần suất dù mỗi khóa hiển thị một lần |

Nếu đang xử lý đơn hàng, lượt truy cập, bản ghi log hoặc điểm số, việc tự ý cho dữ liệu vào `Set` có thể làm **mất những bản ghi lặp có ý nghĩa**. Trái lại, nếu mục tiêu là tập các tên kỹ năng không trùng, việc loại trùng có thể chính là yêu cầu.

**Câu hỏi thiết kế đầu tiên phải là:** cần *giữ mọi lần xuất hiện*, *giữ một phần tử đại diện*, hay *giữ số lần xuất hiện của mỗi nhóm*?

## 2. `List.sort` và `Stream.sorted`: sắp thứ tự, không xóa phần tử

Một `List` cho phép nhiều phần tử bằng nhau xuất hiện tại các vị trí khác nhau. Với `ArrayList` mutable, ta có thể sắp xếp tại chỗ:

```java
// Minh họa một đoạn trong phương thức, không phải chương trình độc lập.
List<String> words = new ArrayList<>(
        List.of("pear", "apple", "pear", "banana", "apple"));
words.sort(Comparator.naturalOrder());
// words: [apple, apple, banana, pear, pear]
```

`List.sort(comparator)` thay đổi thứ tự **ngay trong list**. Các phần tử trùng vẫn chiếm từng vị trí riêng. Nó là phép sắp xếp ổn định (*stable sort*): khi comparator trả `0` cho hai phần tử, thứ tự tương đối ban đầu của chúng được giữ. Nếu list không cho phép thay đổi cấu trúc/nội dung, ví dụ `List.of(...)`, không gọi `sort` trực tiếp trên đó; tạo `new ArrayList<>(source)` hoặc dùng stream.

`Stream.sorted()` tạo một luồng sắp xếp mới, không có tác dụng loại trùng:

```java
// Minh họa một đoạn trong phương thức:
List<String> sorted = source.stream()
        .sorted()
        .toList();
```

Với stream có thứ tự (*ordered stream*), `sorted` được bảo đảm ổn định; với stream không có encounter order, tính ổn định không được bảo đảm. `toList()` trả về danh sách không sửa được bằng các phương thức thay đổi list theo hợp đồng của `Stream.toList()`, nên nếu cần chỉnh sửa sau khi sắp, thu về `ArrayList` thích hợp.

**Không có bước `distinct()` trong hai thao tác trên**, vì vậy số lượng phần tử được giữ nguyên.

## 3. `TreeSet`: vừa sắp xếp vừa loại trùng theo thứ tự so sánh

`TreeSet<E>` thuộc họ `NavigableSet`/`SortedSet`, duy trì các phần tử theo:

- **Thứ tự tự nhiên** của `Comparable`, khi dùng `new TreeSet<>()` và các phần tử có thể so sánh với nhau.
- **Thứ tự do `Comparator` chỉ định**, khi dùng `new TreeSet<>(comparator)`.

Quy tắc phân biệt phần tử của `TreeSet` là:

```text
compare(a, b) < 0  -> a đứng trước b
compare(a, b) = 0  -> a và b được xem là cùng một phần tử theo thứ tự của set
compare(a, b) > 0  -> a đứng sau b
```

Với thứ tự tự nhiên, `compare(a,b)` có nghĩa là `a.compareTo(b)`; với comparator, là `comparator.compare(a,b)`.

Khi thêm một phần tử mới mà phép so sánh với phần tử đang có trả `0`, `TreeSet.add` trả `false` và không thêm một entry thứ hai. `size()` không tăng. Nếu cần biết một phần tử đã có đại diện hay chưa, có thể dùng `contains` theo cùng quy tắc thứ tự, nhưng **không suy ra hai đối tượng giống nhau hoàn toàn về mọi trường**.

Các phép thêm/xóa/tìm kiếm cơ bản trong `TreeSet` được tài liệu Java bảo đảm chi phí theo bậc `log(n)` trong cấu trúc cây. Còn toàn bộ quá trình tạo tập từ `n` phần tử sẽ có chi phí tổng hợp tương ứng với các lần chèn. Sự khác biệt **không chỉ nằm ở hiệu năng**: quan trọng hơn là `TreeSet` loại bớt dữ liệu theo quan hệ tương đương của comparator.

## 4. Ví dụ Java 17+ chạy được: nhìn rõ số lượng và thứ tự

Lưu toàn bộ chương trình thành **`SortVersusSetDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class SortVersusSetDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
                "pear", "apple", "pear", "banana", "apple");

        List<String> sorted = new ArrayList<>(source);
        sorted.sort(Comparator.naturalOrder());

        TreeSet<String> uniqueSorted = new TreeSet<>(source);

        System.out.println("Original: " + source);
        System.out.println("Sorted List: " + sorted);
        System.out.println("TreeSet: " + uniqueSorted);
        System.out.println("Original size: " + source.size());
        System.out.println("TreeSet size: " + uniqueSorted.size());
        System.out.println("Stream distinct then sorted: "
                + source.stream().distinct().sorted().toList());

        TreeMap<String, Integer> counts = new TreeMap<>();
        for (String word : source) {
            counts.merge(word, 1, Integer::sum);
        }
        System.out.println("Sorted frequencies: " + counts);

        List<String> spellings =
                List.of("Java", "java", "JAVA", "Kotlin");
        TreeSet<String> ignoreCase =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCase.addAll(spellings);

        System.out.println("Case-sensitive equals: "
                + "Java".equals("java"));
        System.out.println("Case-insensitive compare zero: "
                + (String.CASE_INSENSITIVE_ORDER
                        .compare("Java", "java") == 0));
        System.out.println("Case-insensitive TreeSet: " + ignoreCase);
        System.out.println("Case-insensitive TreeSet size: "
                + ignoreCase.size());
        System.out.println("Case-insensitive sorted List: "
                + spellings.stream()
                        .sorted(String.CASE_INSENSITIVE_ORDER)
                        .toList());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("BigDecimal equals: " + a.equals(b));
        System.out.println("BigDecimal compareTo zero: "
                + (a.compareTo(b) == 0));

        Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
        Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));
        System.out.println("BigDecimal HashSet size: " + hash.size());
        System.out.println("BigDecimal TreeSet size: " + tree.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SortVersusSetDemo.java
java SortVersusSetDemo
```

Đầu ra xác định:

```text
Original: [pear, apple, pear, banana, apple]
Sorted List: [apple, apple, banana, pear, pear]
TreeSet: [apple, banana, pear]
Original size: 5
TreeSet size: 3
Stream distinct then sorted: [apple, banana, pear]
Sorted frequencies: {apple=2, banana=1, pear=2}
Case-sensitive equals: false
Case-insensitive compare zero: true
Case-insensitive TreeSet: [Java, Kotlin]
Case-insensitive TreeSet size: 2
Case-insensitive sorted List: [Java, java, JAVA, Kotlin]
BigDecimal equals: false
BigDecimal compareTo zero: true
BigDecimal HashSet size: 2
BigDecimal TreeSet size: 1
```

**Giải thích:**

1. `sorted` giữ nguyên 5 phần tử của `source`, chỉ xếp theo thứ tự tự nhiên của `String`. Hai từ `apple` và hai từ `pear` vẫn còn nguyên.
2. `new TreeSet<>(source)` chỉ giữ một bản của mỗi chuỗi trùng theo thứ tự tự nhiên, còn 3 phần tử.
3. `source.stream().distinct().sorted()` cho kết quả giống `TreeSet` **trong ví dụ chuỗi với thứ tự tự nhiên**, vì `String.equals` và `String.compareTo` nhất quán. Hai cách không được coi là tương đương cho mọi comparator.
4. `TreeMap<String,Integer>` dùng mỗi chuỗi làm khóa và cộng số lần xuất hiện; kết quả có thứ tự khóa tăng dần, **không mất tần suất**.
5. `String.CASE_INSENSITIVE_ORDER.compare("Java","java") == 0` nhưng `"Java".equals("java")` là `false`. `TreeSet` dùng comparator này chỉ giữ một phần tử đại diện cho nhóm `Java/java/JAVA`. Vì `"Java"` được thêm đầu tiên, nó là đại diện còn giữ trong ví dụ; `"Kotlin"` là nhóm thứ hai.
6. `spellings.stream().sorted(String.CASE_INSENSITIVE_ORDER)` sắp theo cùng comparator nhưng **giữ cả bốn phần tử**. Với stream có thứ tự từ `List`, các chuỗi có kết quả compare `0` giữ thứ tự tương đối ban đầu.
7. Hai `BigDecimal` có giá trị số học bằng nhau theo `compareTo` nhưng khác `scale`, nên `equals` trả `false`. Vì thế `HashSet` (theo `equals`/`hashCode`) giữ 2 phần tử, trong khi `TreeSet` (theo `compareTo`) giữ 1.

## 5. `equals()` và `compareTo()`: hai quan hệ tương đương có thể khác nhau

Trong Java, `Set` thường gợi liên tưởng “không chứa hai phần tử `equals` bằng nhau”. Nhưng `TreeSet` dùng quan hệ so sánh của nó để thực hiện mọi thao tác xác định phần tử. Do đó, để một `SortedSet` đáp ứng đầy đủ hợp đồng `Set` theo nghĩa của `equals`, thứ tự sắp xếp nên **nhất quán với `equals`**:

```java
// Quy tắc mong muốn khi nói thứ tự nhất quán với equals:
(a.compareTo(b) == 0) == a.equals(b)
```

Nếu hai vế khác nhau, hành vi nội bộ của `TreeSet` vẫn được xác định theo comparator, nhưng nó có thể gây bất ngờ khi so với `HashSet` hoặc quy ước set dựa trên `equals`.

**Trường hợp 1: `compare(a,b) == 0` dù `a.equals(b)` là `false`.** Hai giá trị bị `TreeSet` gộp thành một nhóm. Ví dụ: so sánh `String` không phân biệt hoa/thường, hoặc `BigDecimal("1.0")` và `BigDecimal("1.00")`.

**Trường hợp 2: `a.equals(b)` là `true` nhưng comparator cho kết quả khác `0`.** `TreeSet` có thể giữ hai phần tử mà `equals` coi là bằng nhau, nếu comparator dùng một tiêu chí khác. Đây cũng là sự không nhất quán giữa quan hệ sắp xếp và quan hệ bằng nhau.

Đặc biệt, không được dùng `hashCode()` để đoán `TreeSet` sẽ loại trùng ra sao. `TreeSet` không phân biệt phần tử bằng `hashCode`; nó dùng **thứ tự so sánh**.

### Comparator chỉ so một phần thuộc tính

Giả sử mỗi bản ghi có `name` và `id` độc lập:

```java
record Item(long id, String name) {}

// Một ví dụ về comparator chỉ xét tên:
Comparator<Item> byName = Comparator.comparing(Item::name);
```

Đây là **đoạn minh họa cần đặt trong lớp/phương thức thích hợp**; `record Item` có thể khai báo bên ngoài hoặc trong phạm vi cục bộ hợp lệ. Hai `Item` với ID khác nhau nhưng cùng `name` có `byName.compare(a,b) == 0`, nên `TreeSet<>(byName)` sẽ chỉ giữ một đại diện nếu cả hai được thêm vào. Điều đó đúng nếu tên là khóa phân biệt theo nghiệp vụ, nhưng **sai** nếu bản ghi có ID khác nhau vẫn cần giữ cả hai.

Nếu muốn **sắp xếp theo tên nhưng giữ tất cả bản ghi**, dùng một `List<Item>` và `sort(byName)`. Nếu muốn mỗi ID duy nhất trong `TreeSet` và thứ tự trước hết theo tên, có thể dùng comparator thêm tiêu chí phá hòa (*tie-breaker*) phù hợp:

```java
Comparator<Item> byNameThenId = Comparator
        .comparing(Item::name)
        .thenComparingLong(Item::id);
```

Khi `id` duy nhất và cùng xác định tính bằng nhau, comparator này tránh gộp hai bản ghi chỉ vì trùng tên. Tuy nhiên, nếu `equals` của lớp sử dụng quy tắc khác thì vẫn phải kiểm tra tính nhất quán; thêm `id` không tự động giải quyết mọi mô hình.

## 6. Khi nào dùng `Stream.distinct()`, và cần nhớ điều gì?

`Stream.distinct()` trả về các phần tử phân biệt theo **`Object.equals`**, không nhận một comparator để định nghĩa cách gộp nhóm. Với stream có encounter order (như `List.stream()`), nó giữ phần tử xuất hiện **đầu tiên** trong mỗi nhóm theo `equals`. Sau đó có thể sắp xếp:

```java
// Giữ một bản cho mỗi giá trị equals tương đương, rồi sắp xếp:
List<String> result = source.stream()
        .distinct()
        .sorted()
        .toList();
```

Đây là chuỗi thao tác dễ hiểu khi quy tắc loại trùng là `equals` và tiêu chí sắp xếp là thứ tự tự nhiên. Tuy nhiên:

- `distinct()` **không loại trùng theo comparator tùy chọn**. Với `"Java"` và `"java"`, `distinct()` coi đó là hai chuỗi khác nhau vì `String.equals` phân biệt hoa/thường.
- `sorted(comparator).distinct()` vẫn loại theo `equals`, **không đổi sang quy tắc comparator trả `0`**. Thứ tự hai thao tác có thể ảnh hưởng đại diện/encounter order trong các trường hợp khác nhau; hãy xác định ngữ nghĩa trước.
- Nếu cần loại trùng **theo một khóa nghiệp vụ**, có thể nhóm theo khóa trong `Map`, hoặc dùng comparator phù hợp trong `TreeSet`, nhưng phải xác định rõ đại diện nào được giữ. Không giả định một API ngẫu nhiên chọn “bản mới nhất” hay “bản tốt nhất”.
- Với stream song song có thứ tự, `distinct` có thể đòi hỏi xử lý trạng thái và chi phí đáng kể; hiệu năng không quan trọng bằng tính đúng của quy tắc loại trùng.

`distinct()` cũng dựa trên `equals`/`hashCode` đúng hợp đồng. Nếu lớp tự viết cài đặt `equals` theo giá trị mà quên `hashCode`, kết quả loại trùng dựa trên hash có thể sai. Với `TreeSet`, vấn đề tương ứng là `compareTo`/`Comparator` phải biểu diễn đúng tính tương đương mong muốn.

## 7. Nếu cần cả thứ tự và số lượng của các giá trị lặp

Không nhất thiết phải chọn giữa “mất các bản sao” và “không sắp xếp”. Có nhiều mô hình phù hợp:

| Nhu cầu | Công cụ | Điều cần nhớ |
| --- | --- | --- |
| Sắp xếp và giữ toàn bộ bản ghi | `ArrayList.sort`, `List.sort`, `Stream.sorted` | Có thể có nhiều phần tử bằng nhau |
| Giữ một đại diện mỗi nhóm so sánh và duy trì thứ tự | `TreeSet` | Trùng do comparator trả `0` |
| Loại trùng theo `equals`, sau đó sắp | `stream().distinct().sorted(...)` | Quy tắc loại trùng của `distinct` không phải comparator |
| Đếm tần suất theo khóa có thứ tự | `TreeMap<K,Integer>` cộng dồn | Dữ liệu đếm giữ tổng lần xuất hiện |
| Đếm tần suất theo `equals` rồi trình bày theo thứ tự riêng | `HashMap<K,Integer>` rồi sắp các entry | Quy tắc đếm và quy tắc trình bày có thể khác nhau |
| Loại trùng mà vẫn giữ thứ tự xuất hiện đầu tiên | `LinkedHashSet` hoặc ordered `Stream.distinct` | Thứ tự đầu vào, không phải thứ tự đã sắp |

`TreeMap` cũng dùng comparator/ `compareTo` để xác định **khóa tương đương**. Nếu comparator gộp hai chuỗi khác nhau, `merge` vào `TreeMap` sẽ cộng số lần của cùng một nhóm comparator, không còn đếm từng giá trị `equals` riêng biệt. Đây có thể là chủ đích của báo cáo không phân biệt chữ hoa/thường; nếu không, nó là lỗi phân nhóm.

Nếu yêu cầu là **multiset có thứ tự** (giữ nhiều bản sao của mỗi phần tử), Java Collections Framework không có lớp `TreeMultiset` chuẩn sẵn. Một `TreeMap<K,Integer>` lưu bộ đếm là cách triển khai đơn giản; muốn giữ từng bản ghi chi tiết, `List` đã sắp xếp thường phù hợp hơn. `PriorityQueue` có thể giữ giá trị lặp và lấy phần tử ưu tiên bằng `poll`, nhưng **việc duyệt iterator của queue không được bảo đảm là theo thứ tự sắp xếp**, nên không thay thế trực tiếp danh sách được sắp.

## 8. Những nhầm lẫn thường gặp

1. **“`TreeSet` chỉ sắp xếp, không xóa dữ liệu.”** Sai. Nó có ngữ nghĩa set, loại phần tử tương đương theo comparator.
2. **“`List.sort` tự loại bản ghi trùng.”** Sai. List vẫn giữ đủ số lần xuất hiện.
3. **“`TreeSet` luôn dùng `equals` để phát hiện trùng.”** Sai. `compareTo == 0` hoặc `Comparator.compare == 0` mới là điều kiện xác định cùng phần tử theo thứ tự.
4. **“`TreeSet` trùng với `HashSet` về kết quả.”** Không chắc. `HashSet` dùng `equals`/`hashCode`; `TreeSet` dùng so sánh thứ tự.
5. **“`sorted(comparator).distinct()` loại trùng theo comparator.”** Sai. `distinct` vẫn dùng `equals`.
6. **“Comparator chỉ so tên vẫn giữ mọi người có tên giống nhau.”** Sai nếu cho vào `TreeSet`, vì compare `0` sẽ gộp nhóm.
7. **“Có thể tự do thay đổi trường sắp xếp sau khi thêm vào `TreeSet`.”** Không an toàn. Cấu trúc cây phụ thuộc thứ tự; thay đổi trường tham gia comparator/`compareTo` khi phần tử đang nằm trong set có thể làm tra cứu, xóa, duyệt sai kỳ vọng.
8. **“Có thể dùng `Set` để đếm số lần xuất hiện.”** `Set` chỉ lưu một đại diện mỗi nhóm; để biết tần suất phải đếm riêng hoặc dùng `Map<K,Integer>`.
9. **“Hash bằng nhau nghĩa là `TreeSet` gộp phần tử.”** Không. `TreeSet` không dùng mã băm để phân biệt phần tử.
10. **“Comparator trả `0` chỉ là hai phần tử đứng gần nhau.”** Trong `TreeSet`, `0` còn có nghĩa chúng **không thể cùng tồn tại như hai entry riêng biệt**.

## 9. Checklist trước khi chọn cấu trúc dữ liệu

- **Dữ liệu lặp có ý nghĩa không?** Nếu có, tránh dùng `Set` làm bước sắp xếp mặc định.
- **Quy tắc nào xác định trùng?** `equals`, khóa ID nghiệp vụ, hay comparator (ví dụ không phân biệt hoa/thường)?
- **Một nhóm trùng cần giữ bản đại diện nào?** Bản đầu tiên, bản mới nhất, bản có mức ưu tiên cao nhất hay tổng tần suất?
- **Cần thứ tự khi nào?** Ngay khi thêm phần tử (`TreeSet`, `TreeMap`) hay chỉ khi xuất kết quả (`List.sort`)?
- **Lớp tự viết có nhất quán giữa `equals` và `compareTo` không?** Nếu không, phải hiểu rõ khác biệt giữa `HashSet` và `TreeSet`.
- **Các trường quyết định thứ tự có bất biến không?** Một phần tử trong `TreeSet` không nên bị sửa làm thay đổi vị trí logic của nó.
- **Sau khi xử lý, số phần tử phải bằng số đầu vào hay số nhóm duy nhất?** Đây là kiểm tra nhanh giúp phát hiện thao tác loại trùng ngoài ý muốn.

**Ghi nhớ:** **Sắp xếp** không đồng nghĩa **loại trùng**. Dùng `List.sort`/`Stream.sorted` khi cần giữ tất cả phần tử và chỉ thay đổi thứ tự; dùng `TreeSet` khi thật sự cần tập phần tử duy nhất **theo quan hệ so sánh**; dùng `TreeMap<K,Integer>` khi cần giữ tần suất theo khóa đã sắp xếp. Trước khi đưa đối tượng vào `TreeSet`, luôn kiểm tra `compare(a,b) == 0` có đúng là tiêu chí “trùng” mà nghiệp vụ mong muốn hay không.
