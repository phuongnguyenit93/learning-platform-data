# Đặc tính ORDERED, DISTINCT, SORTED và NONNULL

> **Chương:** Spliterator và nguồn tự định nghĩa  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Hiểu chính xác bốn đặc tính (*characteristics*) của `Spliterator` trong Java Stream API: `ORDERED`, `DISTINCT`, `SORTED` và `NONNULL`. Khi tạo nguồn Stream tùy chỉnh, những cờ này là **lời cam kết về dữ liệu và cách duyệt**, không chỉ là gợi ý tối ưu hóa.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `Spliterator` làm gì trong pipeline lazy và cơ chế chia dữ liệu phục vụ `parallelStream()`.
2. Phân biệt **encounter order** (`ORDERED`), **không trùng theo `equals`** (`DISTINCT`), **thứ tự sắp xếp theo comparator** (`SORTED`) và **không có phần tử null** (`NONNULL`).
3. Nêu đúng các quan hệ và khác biệt: `SORTED` kéo theo `ORDERED`; `ORDERED` không nhất thiết `SORTED`; `DISTINCT` không đồng nghĩa đã sắp xếp.
4. Kiểm tra cờ bằng `characteristics()`/`hasCharacteristics(...)` và hiểu quy tắc `getComparator()`.
5. Viết một `Spliterator` tự định nghĩa có `tryAdvance`, `trySplit`, `estimateSize` và `characteristics` đáp ứng đúng hợp đồng.
6. Kiểm chứng cả phần được tách bởi `trySplit`, thứ tự duyệt, tính duy nhất, null, kích thước và cách chạy tuần tự/song song.
7. Nhận diện rủi ro khi tuyên bố sai cờ, dùng comparator không phù hợp hoặc thay đổi nguồn trong lúc Stream đang xử lý.
8. Hiểu các đặc tính này liên hệ thế nào với `filter`, `map`, `distinct`, `sorted`, `unordered` và tối ưu hóa.

Các ví dụ dùng **Java 17+** để có `List.of`, `List.copyOf` và `Stream.toList()`. Bản thân `Spliterator`, bốn cờ đang học và `StreamSupport` đã có từ **Java 8**. Với Java 8–15, dùng API tương thích như `collect(Collectors.toList())` thay `Stream.toList()`.

---

## 1. Spliterator nằm ở đâu trong Java Stream API?

`Spliterator<T>` là một giao diện dùng để **duyệt** và, khi thích hợp, **chia** các phần tử của một nguồn dữ liệu. Nhiều collection cung cấp nó qua `collection.spliterator()`. `StreamSupport.stream(...)` có thể dùng một Spliterator làm nguồn cho một Stream mới.

~~~text
Collection / mảng / nguồn tùy chỉnh
                  |
                  v
          Spliterator<T>
           |          |
           |          +--- trySplit() ---> Spliterator<T> khác
           |
           +--- tryAdvance(Consumer<T>) / forEachRemaining(...)
                  |
                  v
      Stream<T> (pipeline lazy)
                  |
      filter -> map -> distinct -> sorted -> ...
                  |
                  v
        terminal operation
         collect / reduce / ...
~~~

Ba khía cạnh cần phân biệt:

- **Duyệt:** `tryAdvance` chuyển từng phần tử cho hành động được cung cấp.
- **Phân chia:** `trySplit` có thể tách phần việc còn lại thành những Spliterator khác.
- **Mô tả nguồn:** `characteristics()` trả về tập cờ nói cho Stream biết những bảo đảm thật sự của nguồn.

Một nguồn biết rõ dữ liệu có thứ tự, không trùng, đã sắp xếp và không chứa null có thể công bố các cờ tương ứng. Nhưng nguồn chỉ “thường có vẻ như vậy” không được quyền tuyên bố chúng.

Ví dụ sơ bộ:

~~~java
import java.util.List;
import java.util.Spliterator;

List<Integer> numbers = List.of(4, 1, 4, 2);
Spliterator<Integer> source = numbers.spliterator();

System.out.println(source.hasCharacteristics(Spliterator.ORDERED));
// true: List có encounter order.

System.out.println(source.hasCharacteristics(Spliterator.SORTED));
// false: List không cam kết đã sắp xếp.
~~~

Dù thay dữ liệu thành `List.of(1, 2, 3)`, Spliterator thông thường của List **không nhất thiết tự suy ra `SORTED`**: cờ là đặc tính được nguồn cam kết, không phải một phép kiểm tra dữ liệu ngẫu nhiên ở thời điểm đọc.

## 2. Characteristics là một bitmask, không phải danh sách nhãn

`Spliterator` định nghĩa các hằng kiểu `int`. Có thể kiểm tra chúng bằng:

~~~java
int flags = spliterator.characteristics();

boolean ordered = spliterator.hasCharacteristics(Spliterator.ORDERED);
boolean distinct = spliterator.hasCharacteristics(Spliterator.DISTINCT);
boolean sorted = spliterator.hasCharacteristics(Spliterator.SORTED);
boolean nonNull = spliterator.hasCharacteristics(Spliterator.NONNULL);
~~~

Đây là những **bit** độc lập hoặc có ràng buộc với nhau. Có thể kết hợp bằng toán tử bitwise OR:

~~~java
int flags =
        Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL;
~~~

Khi kiểm tra bằng AND, có thể hỏi một nhóm cờ cùng tồn tại:

~~~java
boolean allFour = spliterator.hasCharacteristics(
        Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL
);
~~~

`hasCharacteristics` chỉ nói về **đặc tính được khai báo**. Nó **không duyệt toàn bộ nguồn để chứng minh** dữ liệu đã thực sự không trùng hay không null. Vì vậy, nếu mã tạo Spliterator tuyên bố sai, phép kiểm tra cờ vẫn trả kết quả theo lời tuyên bố sai ấy.

### 2.1. Bốn cờ chính nhìn trong một bảng

| Cờ | Nguồn cam kết điều gì? | Không cam kết điều gì? |
|---|---|---|
| `ORDERED` | Có encounter order xác định cho quá trình duyệt | Không bảo đảm đã sắp xếp hay mọi lambda chạy theo thứ tự đó |
| `DISTINCT` | Không có hai phần tử khác vị trí nào bằng nhau theo `equals` | Không bảo đảm sắp xếp, không null, hay các khóa phụ khác cũng duy nhất |
| `SORTED` | Duyệt theo một thứ tự sắp xếp xác định; có comparator hoặc natural order | Không bảo đảm không trùng; không mặc nhiên `NONNULL` |
| `NONNULL` | Không có phần tử `null` được phát ra | Không bảo đảm dữ liệu hợp lệ về nghiệp vụ, không đồng nghĩa `DISTINCT` |

Mối quan hệ quan trọng nhất:

~~~text
SORTED ───────> ORDERED      (bắt buộc)
ORDERED ──X──> SORTED       (không suy ra)
DISTINCT ──X─> SORTED       (không suy ra)
SORTED ──X───> DISTINCT     (không suy ra)
NONNULL: độc lập với ba tính chất trên
~~~

Ngoài bốn cờ đang học, `Spliterator` còn có `SIZED`, `SUBSIZED`, `IMMUTABLE`, `CONCURRENT`. Chúng mô tả các bảo đảm khác, không nên lẫn với nội dung/chất lượng của phần tử.

---

## 3. ORDERED: nguồn có encounter order

`Spliterator.ORDERED` nghĩa là nguồn có **encounter order** (thứ tự gặp phần tử) được định nghĩa. Khi duyệt tuần tự với `tryAdvance` hoặc `forEachRemaining`, Spliterator phải phát phần tử theo thứ tự ấy.

Ví dụ nguồn `List`:

~~~java
import java.util.List;
import java.util.Spliterator;

List<String> names = List.of("Bình", "An", "Chi");
Spliterator<String> sp = names.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true

sp.forEachRemaining(System.out::println);
// Bình
// An
// Chi
~~~

Thứ tự này là **thứ tự phần tử trong List**, không phải thứ tự chữ cái. Vì vậy `ORDERED` không đồng nghĩa `SORTED`.

Nguồn có thể có trật tự xác định do:

- **Vị trí:** `List` và mảng.
- **Thứ tự chèn:** những collection như `LinkedHashSet`.
- **Thứ tự theo khóa/comparator:** một `SortedSet`.
- **Quy tắc do nguồn tùy chỉnh thiết lập:** ví dụ bản ghi theo số thứ tự tăng dần.

Ngược lại, các collection như `HashSet` **không cam kết encounter order**. Một lần duyệt có thể trông ổn định, nhưng chương trình không được dựa vào thứ tự đó như một hợp đồng.

### 3.1. Encounter order khác thứ tự thực thi song song

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D");

values.parallelStream().forEach(System.out::println);
// Không bảo đảm A, B, C, D theo thứ tự khi in.

values.parallelStream().forEachOrdered(System.out::println);
// A
// B
// C
// D
~~~

Trong một Stream có thứ tự, `forEachOrdered` giữ encounter order đối với các hành động được thực thi. Điều này có thể làm hạn chế mức song song hữu ích so với `forEach`.

`ORDERED` không có nghĩa tất cả thao tác trong một pipeline song song sẽ **chạy** lần lượt theo vị trí. Framework có thể xử lý phân vùng đồng thời và chỉ duy trì thứ tự ở những thao tác/đầu ra mà hợp đồng yêu cầu.

### 3.2. ORDERED và trySplit()

Với Spliterator có `ORDERED`, `trySplit()` phải trả về một Spliterator bao phủ **tiền tố** (*strict prefix*) của những phần tử còn lại; Spliterator hiện tại giữ phần **hậu tố** tương ứng.

~~~text
Nguồn còn lại: [A, B, C, D, E, F]
                       |
                    trySplit()
                       |
           +-----------+-----------+
           |                       |
     Spliterator trả về     Spliterator ban đầu
          [A, B, C]              [D, E, F]
              tiền tố              hậu tố
~~~

Nếu một nguồn có `ORDERED` nhưng `trySplit` tùy ý trả `[B, D, F]` và giữ `[A, C, E]`, việc tách đó **vi phạm hợp đồng phân chia của nguồn có thứ tự**.

Nếu `trySplit()` trả `null`, nghĩa là lần này Spliterator không chia thêm được. Không có yêu cầu mọi Spliterator phải chia được để gọi là `ORDERED`.

---

## 4. DISTINCT: không có phần tử trùng theo equals

`Spliterator.DISTINCT` nghĩa là **với mọi cặp phần tử khác vị trí**, hai giá trị không bằng nhau theo `Object.equals` (với ngữ nghĩa null phù hợp).

~~~java
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.Spliterator;

Set<String> tags = new LinkedHashSet<>();
tags.add("java");
tags.add("stream");
tags.add("java"); // Không tạo phần tử thứ hai.

Spliterator<String> sp = tags.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.DISTINCT)); // true
System.out.println(tags); // [java, stream]
~~~

`Set` theo hợp đồng tập hợp không chứa hai phần tử bằng nhau theo `equals`. `LinkedHashSet` còn có encounter order theo thứ tự chèn, nhưng **DISTINCT tự nó không yêu cầu ORDERED**.

### 4.1. DISTINCT không có nghĩa duy nhất theo mọi thuộc tính

~~~java
import java.util.List;
import java.util.stream.Collectors;

record Product(long id, String category) {}

List<Product> products = List.of(
        new Product(1L, "BOOK"),
        new Product(2L, "BOOK"),
        new Product(3L, "PEN")
);
~~~

Ba record này khác nhau theo `equals` nên các đối tượng có thể đều DISTINCT, nhưng **category không duy nhất**: có hai sản phẩm thuộc `BOOK`. Nếu đang lập chỉ mục bằng `Collectors.toMap(Product::category, ...)`, khóa trùng vẫn xảy ra.

Điều kiện “không có phần tử trùng theo `equals`” khác “không có ID trùng”, “không có email trùng” hoặc “không có category trùng” nếu `equals` của kiểu phần tử không chỉ dựa vào thuộc tính ấy.

### 4.2. DISTINCT không đồng nghĩa SORTED

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

Set<Integer> numbers = new LinkedHashSet<>();
numbers.add(9);
numbers.add(1);
numbers.add(5);

System.out.println(numbers); // [9, 1, 5]
~~~

Các phần tử không trùng, nhưng không được sắp tăng. Cũng có thể có nguồn **SORTED mà không DISTINCT**, chẳng hạn dãy `[1, 1, 2, 3]`.

### 4.3. Cảnh báo với comparator không nhất quán với equals

Một `Comparator` có thể coi hai giá trị tương đương khi `compare(a, b) == 0` trong khi `a.equals(b)` trả `false`, hoặc ngược lại. Vì vậy, **chứng minh các khóa khác nhau theo comparator chưa đủ để kết luận `DISTINCT` theo `equals`**.

Khi tự viết nguồn `SORTED | DISTINCT`, hãy xác minh cả:

1. Dữ liệu đúng thứ tự theo comparator đã công bố.
2. Không có hai phần tử bằng nhau theo `equals`.

Trong ví dụ nguồn `Integer` tăng nghiêm ngặt ở mục 10, natural ordering nhất quán với `equals` nên kiểm tra `previous < current` bảo đảm được cả hai điều kiện.

---

## 5. SORTED: thứ tự sắp xếp có hợp đồng

`Spliterator.SORTED` nghĩa là phần tử được duyệt theo một thứ tự sắp xếp xác định:

- **Natural order** của phần tử, nếu nguồn dùng thứ tự tự nhiên; hoặc
- Một **`Comparator`** được nguồn cung cấp.

Một Spliterator khai báo `SORTED` **bắt buộc** cũng phải khai báo `ORDERED`.

~~~java
import java.util.SortedSet;
import java.util.Spliterator;
import java.util.TreeSet;

SortedSet<Integer> sorted = new TreeSet<>();
sorted.add(9);
sorted.add(1);
sorted.add(5);

Spliterator<Integer> sp = sorted.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SORTED));  // true

sp.forEachRemaining(System.out::println);
// 1
// 5
// 9
~~~

Thứ tự tăng dần ở đây do natural ordering của `Integer`, không phải do tình cờ danh sách đã sắp xếp.

### 5.1. getComparator() là một phần của hợp đồng SORTED

Nếu Spliterator có `SORTED`, `getComparator()` phải:

- Trả `null` khi nguồn sắp xếp theo **natural order**.
- Trả `Comparator<? super T>` phù hợp nếu dùng thứ tự riêng.

Nếu Spliterator **không** có `SORTED`, lời gọi `getComparator()` phải ném `IllegalStateException`.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;

Spliterator<Integer> natural =
        new TreeSet<>(List.of(3, 1, 2)).spliterator();

System.out.println(natural.getComparator() == null); // true

TreeSet<String> reversed = new TreeSet<>(
        Comparator.reverseOrder()
);
reversed.addAll(List.of("An", "Bình", "Chi"));

Spliterator<String> customOrder = reversed.spliterator();

System.out.println(customOrder.getComparator() != null); // true

Spliterator<Integer> listSp = List.of(1, 2, 3).spliterator();

try {
    listSp.getComparator(); // List spliterator không công bố SORTED.
} catch (IllegalStateException expected) {
    System.out.println("Nguồn không khai báo SORTED");
}
~~~

**Sai lầm thường gặp:** override `getComparator()` trả `null` chỉ để “cho qua” dù cờ `SORTED` không có; hoặc công bố `SORTED` nhưng lại trả comparator không phản ánh thứ tự phần tử thực sự.

### 5.2. SORTED không bảo đảm không trùng

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);

System.out.println(
        values.stream().sorted().toList()
); // [1, 1, 2, 3]
~~~

`sorted()` sắp xếp nhưng không loại phần tử trùng. Nếu cần hai đặc tính, thường phải dùng cả `sorted()` lẫn `distinct()` (trừ khi nguồn đã cam kết một trong hai).

### 5.3. Đừng tự khai báo SORTED cho một List chỉ vì vừa kiểm tra dữ liệu

Một `List.of(1, 2, 3)` có nội dung tăng dần ở ví dụ hiện tại, nhưng kiểu nguồn List tổng quát không tự cam kết tính chất đó cho mọi đối tượng List. Trong một nguồn tùy chỉnh, việc **cố định snapshot và kiểm tra trước** khi công bố `SORTED` có thể hợp lệ; đó là chiến lược được dùng ở mục 10.

---

## 6. NONNULL: nguồn cam kết không phát ra null

`Spliterator.NONNULL` nói rằng tất cả phần tử được Spliterator phát ra đều **khác `null`**.

~~~java
import java.util.List;
import java.util.Spliterator;

List<String> names = List.of("An", "Bình", "Chi");

// List.of không chấp nhận phần tử null.
boolean noNullInData = names.stream().noneMatch(v -> v == null);
System.out.println(noNullInData); // true
~~~

**Tuy nhiên:** từ việc dữ liệu trong List hiện không null **không được suy ra** rằng `names.spliterator()` bắt buộc công bố cờ `NONNULL`. Đây là một đặc tính của **triển khai Spliterator**, không phải một phép suy luận chạy trên List.

Một nguồn tùy chỉnh có thể công bố `NONNULL` nếu cấu trúc dữ liệu, quá trình kiểm tra đầu vào hoặc giao thức phát phần tử bảo đảm không có null.

### 6.1. NONNULL không thay thế kiểm tra hợp lệ nghiệp vụ

~~~java
record Employee(String name, int age) {}

Employee e = new Employee("", -5);
System.out.println(e != null); // true
~~~

Đối tượng không null nhưng nội dung có thể không hợp lệ theo nghiệp vụ. `NONNULL` không chứng nhận tuổi dương, tên có giá trị, email đúng định dạng hoặc bất kỳ quy tắc domain nào.

### 6.2. Không khai báo NONNULL nếu nguồn có thể phát null

~~~java
import java.util.Arrays;
import java.util.List;

List<String> source = Arrays.asList("An", null, "Chi");

// Ví dụ xử lý rõ null trước khi gọi String::length.
List<Integer> lengths = source.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::length)
        .toList();

System.out.println(lengths); // [2, 3]
~~~

Nếu nguồn có khả năng phát null, tự công bố `NONNULL` là sai. Việc gọi `filter(Objects::nonNull)` trong pipeline có thể xử lý null ở tầng ứng dụng, nhưng không “sửa” được một **khai báo sai của nguồn** có thể đã ảnh hưởng đến cách Stream tối ưu thao tác.

### 6.3. NONNULL không làm mọi terminal operation an toàn với null

Ví dụ `Stream.findFirst()` trả `Optional<T>` và không thể biểu diễn một giá trị được chọn là null bằng `Optional.of(null)`:

~~~java
import java.util.stream.Stream;

// Có thể ném NullPointerException do phần tử đầu tiên là null.
// Stream.of((String) null).findFirst();
~~~

Nguồn có thể chứa null cần một chính sách xử lý riêng. Không nên lấy `NONNULL` làm cách “tắt” kiểm tra null đối với một nguồn không được kiểm chứng.

---

## 7. Bảng phân biệt các tổ hợp đặc tính

Đừng đọc bốn cờ như bốn mức độ “chất lượng” tăng dần. Chúng mô tả **bốn chiều thông tin khác nhau**:

| Nguồn dữ liệu về mặt khái niệm | ORDERED | DISTINCT | SORTED | NONNULL |
|---|---|---|---|---|
| Dãy `[3, 1, 3]` theo vị trí | Có | Không | Không | Có, nếu bảo đảm |
| Dãy `[1, 1, 3]` có sắp tăng | Có | Không | Có | Có, nếu bảo đảm |
| Tập `{3, 1, 5}` không có thứ tự duyệt quy định | Không | Có | Không | Tùy nguồn |
| Tập số nguyên tự nhiên sắp tăng `[1, 3, 5]` | Có | Có | Có | Có, nếu bảo đảm |
| Dãy `[null, "A"]` có thứ tự vị trí | Có | Có nếu hai phần tử khác nhau theo equals | Có thể, nếu comparator hỗ trợ null | Không |

Bảng mô tả **các bảo đảm có thể có**; không khẳng định mọi implementation Java của một collection cụ thể tự động xuất ra đúng tập cờ như hàng tương ứng.

### 7.1. Một số ví dụ collection phổ biến

| Loại nguồn | Điều thường có thể dựa vào |
|---|---|
| `List` | Có encounter order; không tự mặc định DISTINCT hoặc SORTED |
| `LinkedHashSet` | Không trùng theo Set và duyệt theo thứ tự chèn |
| `HashSet` | Không trùng theo Set; không bảo đảm encounter order |
| `SortedSet`/`TreeSet` | Có thứ tự sắp xếp theo comparator/natural order |
| `StreamSupport.stream(customSpliterator, ...)` | Phụ thuộc hoàn toàn vào hợp đồng của Spliterator được cung cấp |

Trong mã thực tế, kiểm tra flags nếu việc ra quyết định phụ thuộc vào chúng; song song với đó phải **kiểm chứng chính triển khai nguồn** để bảo đảm flags phản ánh dữ liệu thật.

---

## 8. Kiểm tra flags qua API

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> sp = List.of(5, 1, 5).spliterator();

int flags = sp.characteristics();

System.out.println(
        (flags & Spliterator.ORDERED) != 0
);

System.out.println(
        sp.hasCharacteristics(Spliterator.ORDERED)
);

System.out.println(
        sp.hasCharacteristics(
                Spliterator.ORDERED | Spliterator.SIZED
        )
);
~~~

Khi truyền nhiều bit cho `hasCharacteristics`, kết quả chỉ `true` nếu **tất cả bit được yêu cầu** đều có.

### 8.1. Các phương thức thường đi kèm

| Phương thức | Mục đích |
|---|---|
| `characteristics()` | Trả bitmask các đặc tính nguồn |
| `hasCharacteristics(flags)` | Kiểm tra mọi cờ yêu cầu có được công bố không |
| `estimateSize()` | Ước lượng số phần tử còn lại |
| `getExactSizeIfKnown()` | Kích thước chính xác nếu có `SIZED`, ngược lại trả `-1` |
| `tryAdvance(action)` | Phát nhiều nhất một phần tử và báo còn hay hết |
| `forEachRemaining(action)` | Phát các phần tử còn lại |
| `trySplit()` | Tách một phần nguồn còn lại hoặc trả `null` |
| `getComparator()` | Chỉ có ý nghĩa nếu `SORTED` |

Ví dụ kiểm tra an toàn `getComparator`:

~~~java
import java.util.Comparator;
import java.util.Spliterator;

static <T> Comparator<? super T> comparatorIfSorted(
        Spliterator<T> sp) {

    if (!sp.hasCharacteristics(Spliterator.SORTED)) {
        throw new IllegalArgumentException("Nguồn chưa công bố SORTED");
    }

    return sp.getComparator();
    // null có nghĩa natural ordering; không phải comparator bị lỗi.
}
~~~

Đoạn trên đặt bên trong lớp tiện ích Java. Nếu cần so sánh theo natural order khi comparator là `null`, hãy xác định rõ rằng kiểu phần tử thực sự hỗ trợ `Comparable` theo hợp đồng nguồn.

---

## 9. Khi nào được công bố bốn cờ trong nguồn tự định nghĩa?

Trước khi viết `characteristics()` cho Spliterator tùy chỉnh, đặt bốn câu hỏi:

1. **ORDERED:** Nguồn có một thứ tự duyệt được định nghĩa không? Nếu `trySplit` tách nguồn, phần tách ra có là tiền tố của phần còn lại không?
2. **DISTINCT:** Mỗi cặp phần tử khác vị trí có bảo đảm không bằng nhau theo `equals` không? Nếu khóa phụ trùng thì không tự làm phần tử mất DISTINCT.
3. **SORTED:** Các phần tử có thực sự theo natural order hoặc comparator đã công bố không? Có khai báo ORDERED và triển khai `getComparator` đúng không?
4. **NONNULL:** Mọi đường phát phần tử đều không thể tạo null không? Việc nguồn thay đổi trong lúc duyệt có phá vỡ bảo đảm này không?

Đặc tính phải đúng cho **toàn bộ quá trình sử dụng Spliterator**, không chỉ đúng với vài phần tử đầu tiên hoặc trong dữ liệu mẫu.

Một cách đơn giản, dễ kiểm chứng là:

- Tạo snapshot bất biến của nguồn đầu vào.
- Xác thực dữ liệu và thứ tự khi tạo snapshot.
- Duyệt bằng cặp chỉ số `[index, fence)`.
- Khi chia, tạo Spliterator con trên **tiền tố** `[index, mid)`, còn Spliterator ban đầu giữ `[mid, fence)`.
- Bảo đảm mọi Spliterator con sử dụng cùng tập cờ phản ánh đúng các lát của snapshot.

Phần tiếp theo biến cách làm ấy thành chương trình chạy được.

---

## 10. Ví dụ hoàn chỉnh: nguồn Integer tăng nghiêm ngặt, không null

Nguồn mẫu có những bảo đảm rõ ràng:

- Giá trị kiểu `Integer`, không có null.
- Các phần tử được sắp **tăng nghiêm ngặt** theo natural order.
- Không có phần tử trùng theo `equals`.
- Thứ tự gặp phần tử chính là thứ tự tăng.
- Snapshot không bị sửa cấu trúc sau khi tạo.
- Mỗi Spliterator biết chính xác số phần tử còn lại và có thể tách theo lát chỉ số.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class SortedUniqueSpliteratorDemo {

    static final class SortedUniqueIntegers
            implements Spliterator<Integer> {

        private final List<Integer> data;
        private int index;
        private final int fence;

        // Constructor công khai: sao chép và xác thực dữ liệu nguồn.
        SortedUniqueIntegers(List<Integer> input) {
            Objects.requireNonNull(input, "input");

            // List.copyOf không cho phép phần tử null.
            List<Integer> snapshot = List.copyOf(input);

            for (int i = 1; i < snapshot.size(); i++) {
                if (snapshot.get(i - 1) >= snapshot.get(i)) {
                    throw new IllegalArgumentException(
                            "Giá trị phải tăng nghiêm ngặt ở vị trí " + i
                    );
                }
            }

            this.data = snapshot;
            this.index = 0;
            this.fence = snapshot.size();
        }

        // Constructor nội bộ: chia sẻ snapshot bất biến theo một lát.
        private SortedUniqueIntegers(
                List<Integer> snapshot, int index, int fence) {
            this.data = snapshot;
            this.index = index;
            this.fence = fence;
        }

        @Override
        public boolean tryAdvance(
                Consumer<? super Integer> action) {
            Objects.requireNonNull(action, "action");

            if (index >= fence) {
                return false;
            }

            action.accept(data.get(index++));
            return true;
        }

        @Override
        public Spliterator<Integer> trySplit() {
            int remaining = fence - index;

            if (remaining <= 1) {
                return null;
            }

            int middle = index + remaining / 2;

            // Trả lại tiền tố của phần tử còn lại.
            SortedUniqueIntegers prefix =
                    new SortedUniqueIntegers(data, index, middle);

            // Spliterator hiện tại giữ hậu tố.
            index = middle;

            return prefix;
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return ORDERED
                    | DISTINCT
                    | SORTED
                    | NONNULL
                    | SIZED
                    | SUBSIZED
                    | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // Nguồn SORTED theo natural ordering của Integer.
            return null;
        }
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(1, 3, 7, 9, 11);

        SortedUniqueIntegers source =
                new SortedUniqueIntegers(values);

        int required = Spliterator.ORDERED
                | Spliterator.DISTINCT
                | Spliterator.SORTED
                | Spliterator.NONNULL;

        System.out.println(source.hasCharacteristics(required));
        // true

        System.out.println(source.getComparator() == null);
        // true: natural order

        List<Integer> sequential = StreamSupport.stream(
                new SortedUniqueIntegers(values), false
        ).toList();

        List<Integer> parallel = StreamSupport.stream(
                new SortedUniqueIntegers(values), true
        ).toList();

        System.out.println(sequential); // [1, 3, 7, 9, 11]
        System.out.println(parallel);   // [1, 3, 7, 9, 11]
    }
}
~~~

### 10.1. Vì sao ví dụ được phép khai báo bốn cờ?

| Cờ | Chứng cứ từ triển khai |
|---|---|
| `ORDERED` | Duyệt theo chỉ số tăng và `trySplit` trả lát **tiền tố** |
| `DISTINCT` | Constructor từ chối mọi cặp kề không tăng; với `Integer` natural order nhất quán với `equals` |
| `SORTED` | Snapshot được kiểm tra tăng nghiêm ngặt; `getComparator()` trả `null` để chỉ natural order |
| `NONNULL` | `List.copyOf` từ chối phần tử null trước khi nguồn được công bố |

Các cờ bổ sung:

- `SIZED`: `fence - index` là số phần tử còn lại chính xác.
- `SUBSIZED`: sau khi chia, cả phần tách ra và phần giữ lại đều biết kích thước chính xác.
- `IMMUTABLE`: nguồn duyệt được xây từ snapshot không thể thay đổi cấu trúc, chứa các giá trị `Integer` bất biến.

**Giới hạn:** Đây là nguồn minh họa chuyên biệt cho `Integer` tăng nghiêm ngặt. Không thể sao chép nguyên cờ `DISTINCT | SORTED | NONNULL` sang một nguồn tùy ý mà không có bảo đảm tương ứng.

### 10.2. Vì sao phải tạo Spliterator mới cho mỗi Stream?

~~~java
// Nên tạo nguồn mới cho mỗi lần sử dụng:
List<Integer> a = StreamSupport.stream(
        new SortedUniqueIntegers(values), false
).toList();

List<Integer> b = StreamSupport.stream(
        new SortedUniqueIntegers(values), true
).toList();
~~~

`Spliterator` thường giữ vị trí duyệt thay đổi. Nếu một Stream đã tiêu thụ Spliterator, việc dùng lại đối tượng đó cho Stream khác có thể chỉ còn các phần tử chưa duyệt hoặc không còn phần tử nào. **Không dùng lại một nguồn đã bị tiêu thụ rồi tưởng đó là hai phép đọc độc lập.**

---

## 11. Kiểm tra trySplit: tiền tố, hậu tố và tính duy nhất

Xét một nguồn có thứ tự:

~~~text
[1, 3, 7, 9, 11, 15]

trySplit:
  trả về:       [1, 3, 7]
  giữ lại:      [9, 11, 15]

Khi duyệt lần lượt phần trả về, rồi phần giữ lại:
  [1, 3, 7, 9, 11, 15]
~~~

Để kiểm tra trực tiếp, đặt đoạn sau trong `SortedUniqueSpliteratorDemo.main`:

~~~java
List<Integer> values = List.of(1, 3, 7, 9, 11, 15);

SortedUniqueIntegers remainder =
        new SortedUniqueIntegers(values);

Spliterator<Integer> prefix = remainder.trySplit();

if (prefix == null) {
    throw new AssertionError("Nguồn đủ lớn phải tách được");
}

List<Integer> left = StreamSupport.stream(prefix, false).toList();
List<Integer> right = StreamSupport.stream(remainder, false).toList();

System.out.println(left);  // [1, 3, 7]
System.out.println(right); // [9, 11, 15]

java.util.ArrayList<Integer> recombined =
        new java.util.ArrayList<>(left);
recombined.addAll(right);

if (!recombined.equals(values)) {
    throw new AssertionError("Mất, nhân đôi hoặc đảo phần tử");
}
~~~

Đoạn này kiểm tra một lần tách. Với một Spliterator phức tạp, nên lặp tách **nhiều cấp**, kiểm tra tất cả các phần đều:

- Không phát phần tử ngoài nguồn.
- Không làm mất hoặc nhân đôi phần tử.
- Giữ đúng encounter order nếu `ORDERED`.
- Không phát null nếu `NONNULL`.
- Không tạo phần tử trùng theo `equals` nếu `DISTINCT`.
- Giữ comparator/order của phần tách nếu `SORTED`.
- Có kích thước chính xác khi `SIZED | SUBSIZED` được công bố.

### 11.1. Cờ sau khi tách

~~~java
int flags = Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL;

SortedUniqueIntegers source =
        new SortedUniqueIntegers(List.of(1, 2, 5, 8));

Spliterator<Integer> prefix = source.trySplit();

System.out.println(prefix != null
        && prefix.hasCharacteristics(flags)); // true

System.out.println(source.hasCharacteristics(flags)); // true
~~~

Cả hai lát cùng trỏ đến snapshot đã xác thực và chia theo tiền tố/hậu tố, nên bốn bảo đảm vẫn đúng sau khi tách.

---

## 12. Cờ của nguồn ảnh hưởng gì đến Stream pipeline?

Stream API dùng thông tin từ nguồn và các thao tác trung gian để lập kế hoạch xử lý. Một số phép toán có thể tận dụng đặc tính đã biết:

- `distinct()` có thể tránh làm việc không cần thiết nếu dữ liệu đã được bảo đảm `DISTINCT`.
- `sorted()` có thể tránh sắp xếp lại nếu nguồn/pipeline đã được bảo đảm sắp tự nhiên đúng yêu cầu.
- Thứ tự gặp phần tử có thể tác động đến `findFirst`, `limit`, `forEachOrdered` và nhiều thao tác trạng thái, nhất là khi song song.
- `SIZED`/`SUBSIZED` (ngoài phạm vi bốn cờ chính) có thể giúp phân chia, cấp phát hoặc tối ưu đếm.

Những điểm trên là **khả năng tối ưu hợp lệ**, không phải bảo đảm một phiên bản JDK cụ thể sẽ bỏ qua hay thực hiện bao nhiêu thao tác.

### 12.1. filter giữ nội dung phần tử nhưng thay đổi số lượng

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 7, 9, 11);

List<Integer> result = values.stream()
        .filter(n -> n > 5)
        .toList();

System.out.println(result); // [7, 9, 11]
~~~

Về ngữ nghĩa dữ liệu, chỉ lọc bỏ phần tử của một dãy vốn SORTED/DISTINCT/NONNULL thì các phần tử còn lại vẫn có các tính chất đó và còn encounter order như trước.

Tuy nhiên, `filter` làm số lượng phần tử không còn suy ra trực tiếp từ số lượng nguồn. **Đừng mặc định bitmask của Spliterator sau mọi thao tác trung gian sẽ giống hệt bitmask nguồn**; Stream có các quy tắc duy trì/hủy thông tin riêng.

### 12.2. map có thể làm mất DISTINCT, SORTED, NONNULL

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 5);

List<Integer> mapped = values.stream()
        .map(n -> n % 2)
        .toList();

System.out.println(mapped); // [1, 1, 1]
~~~

Ngay cả nếu nguồn đầu vào không trùng và đã sắp xếp, phép `map` tổng quát có thể:

- Tạo **trùng** do nhiều phần tử đi về cùng giá trị.
- Làm **mất thứ tự sắp xếp** do hàm biến đổi không đơn điệu.
- Trả **null** ngay cả khi đầu vào không null.

Do đó không được tự suy ra `DISTINCT`, `SORTED` hoặc `NONNULL` cho đầu ra của một phép `map` tùy ý. Nếu một pipeline có hành vi đặc biệt bảo toàn những tính chất ấy, đó phải là bảo đảm được đánh giá riêng.

### 12.3. distinct(), sorted() và unordered()

~~~java
import java.util.List;

List<Integer> numbers = List.of(3, 1, 3, 2);

System.out.println(numbers.stream().distinct().toList());
// [3, 1, 2]: nguồn có thứ tự, giữ lần gặp đầu tiên.

System.out.println(numbers.stream().sorted().toList());
// [1, 2, 3, 3]: đã sắp xếp nhưng còn số 3 trùng.

System.out.println(numbers.stream()
        .distinct().sorted().toList());
// [1, 2, 3]
~~~

`unordered()` là thao tác trung gian có thể **bỏ ràng buộc encounter order của Stream**, để framework có thêm tự do khi tối ưu. Nó **không hứa sẽ xáo trộn phần tử**, cũng không đồng nghĩa phần tử mất DISTINCT hay phải chứa null.

~~~java
List<Integer> result = numbers.parallelStream()
        .unordered()
        .distinct()
        .toList();

// Không dựa vào thứ tự phần tử trong result nếu pipeline không
// còn ràng buộc encounter order.
~~~

**Không thay cờ nguồn để ép thứ tự mong muốn**. Nếu muốn sắp xếp, dùng `sorted` với comparator thích hợp; nếu muốn bỏ trùng, dùng `distinct` hoặc cấu trúc tập hợp theo đúng chính sách `equals`.

---

## 13. Cảnh báo: khai báo sai characteristics có thể làm sai kết quả

Một nguồn chưa được xác thực:

~~~text
Dữ liệu: [1, 1, 2]
Thực tế:
  ORDERED = có, theo vị trí
  DISTINCT = không
  SORTED = có, theo số tự nhiên
  NONNULL = có, nếu dữ liệu không null
~~~

Nếu mã nguồn tùy chỉnh **khai báo `DISTINCT` một cách không đúng**, một triển khai Stream có thể tin rằng không cần loại phần tử trùng nữa và tối ưu `distinct()`. Khi ấy kết quả có nguy cơ vẫn chứa hai số `1`.

~~~java
// KHÔNG làm:
// characteristics() trả DISTINCT khi nguồn thực tế chứa [1, 1, 2].
//
// StreamSupport.stream(broken, false)
//         .distinct()
//         .toList();
//
// Không dùng kết quả để suy ra Stream đã sửa dữ liệu sai của nguồn.
~~~

Tương tự:

- Khai báo `SORTED` cho dữ liệu chưa sắp xếp có thể khiến `sorted()` không thực hiện công việc mà người viết mong đợi.
- Khai báo `ORDERED` nhưng `trySplit` không trả đúng tiền tố có thể làm hỏng kết quả phụ thuộc encounter order.
- Khai báo `NONNULL` trong khi nguồn có thể phát null là **vi phạm hợp đồng** và làm các giả định của mã sử dụng nguồn không còn hợp lệ.
- Khai báo `SIZED` với `estimateSize` không chính xác có thể làm các tối ưu dựa vào kích thước bị sai.

Nguyên tắc: **khai báo ít hơn những gì nguồn thật sự biết thường làm mất cơ hội tối ưu; khai báo nhiều hơn sự thật có thể làm sai kết quả.** Đừng thêm cờ chỉ vì một benchmark hoặc một bộ dữ liệu mẫu trông “đã đúng”.

---

## 14. Custom source không biết trước kích thước

Không phải nguồn nào cũng có dữ liệu nằm trong một `List` hoặc biết kích thước trước khi duyệt. Ví dụ một `Iterator<String>` do ứng dụng cung cấp:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
);

List<String> values = StreamSupport.stream(source, false).toList();

System.out.println(values); // [A, B, C]
~~~

Ở ví dụ này:

- Thứ tự của iterator bắt nguồn từ `List` nên có thể công bố `ORDERED`.
- `List.of` không chứa null và iterator chỉ trả phần tử của List nên có thể công bố `NONNULL`.
- Không tự công bố `SIZED` vì cách tạo `spliteratorUnknownSize` không biết trước tổng số phần tử.
- Không công bố `DISTINCT` hay `SORTED` vì đầu vào mẫu này không đủ tạo ra hợp đồng tổng quát cho mọi nguồn tương tự.

Khi sử dụng trên iterator thực sự từ mạng, file hay truy vấn dữ liệu, cần hiểu nguồn có thể thay đổi, số lượng có thể tăng, có thể lỗi và cần giải phóng tài nguyên. `Spliterators.spliteratorUnknownSize` không tự đóng tài nguyên của iterator.

### 14.1. Nguồn vô hạn và giới hạn duyệt

~~~java
import java.util.stream.Stream;

List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

Ví dụ này là Stream sinh phần tử theo nhu cầu chứ không yêu cầu tự viết Spliterator. Nó cho thấy có những nguồn không biết trước số lượng cuối; khi đó không nên tuyên bố `SIZED` nếu không có một kích thước chính xác hợp lệ.

Dữ liệu tự sinh có tăng dần không tự bảo đảm mọi loại nguồn vô hạn đều `SORTED`; nếu tự viết Spliterator và công bố `SORTED`, cần chứng minh thứ tự theo comparator cho mọi phần tử thực sự được phát.

---

## 15. IMMUTABLE, CONCURRENT và sự ổn định của bốn cờ

Bốn cờ `ORDERED`/`DISTINCT`/`SORTED`/`NONNULL` mô tả dữ liệu; còn `IMMUTABLE` và `CONCURRENT` liên quan đến cách nguồn đối diện **sửa đổi trong lúc duyệt**.

| Cờ bổ sung | Ý nghĩa chính | Không đồng nghĩa |
|---|---|---|
| `IMMUTABLE` | Nguồn phần tử không thể bị thay đổi cấu trúc trong lúc duyệt | Không có nghĩa mọi đối tượng phần tử là immutable sâu |
| `CONCURRENT` | Nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng của nó | Không tự bảo đảm DISTINCT/SORTED/NONNULL |
| `SIZED` | Số phần tử còn lại được biết chính xác theo hợp đồng | Không đồng nghĩa thứ tự đã sắp xếp |
| `SUBSIZED` | Các Spliterator sau chia có kích thước chính xác theo hợp đồng | Không đồng nghĩa chia cân bằng hoặc luôn chia được |

Một nguồn tùy chỉnh dựa trên collection mutable bị thread khác sửa trong lúc duyệt có thể phá vỡ bảo đảm đã công bố. Ví dụ:

- Dữ liệu đang sắp xếp tăng nhưng bị thay đổi chèn vào giữa có thể không còn `SORTED`.
- Dữ liệu không trùng lúc tạo, nhưng có thêm giá trị trùng trong quá trình duyệt sẽ phá `DISTINCT`.
- Trường tham chiếu trong các đối tượng mutable có thể chuyển thành null, khiến các giả định nghiệp vụ sai — dù bản thân phần tử gốc không null.

Tạo snapshot và chỉ đọc là một cách đơn giản để tránh vấn đề đó. Khi dữ liệu phải cập nhật liên tục, cần chọn cấu trúc dữ liệu và hợp đồng nguồn thích hợp; chỉ thêm `CONCURRENT` vào bitmask không làm một collection bất kỳ tự động an toàn cho truy cập đồng thời.

### 15.1. SIZED và biến đổi sau nguồn

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

long count = values.stream()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(count); // 2
~~~

Nguồn `List` biết số phần tử, nhưng sau `filter` số phần tử còn lại phụ thuộc predicate. Một thao tác trung gian có thể làm một đặc tính về số lượng không còn áp dụng cho pipeline kết quả. Đây là một trong các lý do không nên coi flags của nguồn và flags của mọi pipeline là một thứ.

---

## 16. Đặc tính với primitive Spliterator

Java còn có:

- `Spliterator.OfInt`.
- `Spliterator.OfLong`.
- `Spliterator.OfDouble`.

Các kiểu chuyên biệt này cho phép duyệt giá trị nguyên thủy mà không cần boxing vào `Integer`/`Long`/`Double` ở mỗi bước.

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt ints = IntStream.range(0, 5).spliterator();

System.out.println(ints.hasCharacteristics(Spliterator.ORDERED));
// true

System.out.println(ints.hasCharacteristics(Spliterator.SORTED));
// true

System.out.println(ints.getComparator() == null);
// true: thứ tự tự nhiên trong nguồn range.
~~~

`IntStream.range(0, 5)` cung cấp dãy số `0,1,2,3,4` tăng dần, không trùng và hữu hạn. Các bảo đảm của nguồn `range` phải được đọc theo hợp đồng của nguồn này; không áp chúng cho một `IntStream` tùy ý đã qua `map`.

### 16.1. NONNULL với kiểu nguyên thủy

`int`/`long`/`double` nguyên thủy **không thể là null**. Tuy nhiên, việc một primitive Spliterator công bố cờ `NONNULL` hay không vẫn là chi tiết/hợp đồng của Spliterator cụ thể; khi lập trình, không cần dùng `Integer` boxing chỉ để kiểm tra null của dữ liệu primitive.

Nếu chuyển dữ liệu qua `mapToObj` và trả object, code mapping **có thể trả null**. Khi ấy không còn được suy ra nguồn đối tượng có `NONNULL` chỉ vì nguồn số nguyên ban đầu không có null.

---

## 17. Kiểm thử nguồn tùy chỉnh: đừng chỉ so sequential và parallel

Một nguồn Spliterator tốt cần kiểm chứng **bốn chiều nội dung và hợp đồng chia**. Bảng thử nghiệm đề xuất:

| Ca kiểm thử | Điều cần kiểm tra |
|---|---|
| Nguồn rỗng | `tryAdvance` trả false, `estimateSize` bằng 0; không phát phần tử |
| Một phần tử | Không mất/nhân đôi, `trySplit` có thể trả null |
| Nhiều phần tử | Duyệt tuần tự đúng thứ tự gốc |
| Tách 2 phần | Spliterator trả về bao phủ tiền tố, phần giữ lại bao phủ hậu tố |
| Tách nhiều cấp | Ghép các phần theo đúng thứ tự không mất/nhân đôi |
| Dữ liệu trùng | Constructor nguồn DISTINCT từ chối hoặc không khai báo DISTINCT |
| Dữ liệu chưa sắp | Constructor nguồn SORTED từ chối hoặc không khai báo SORTED |
| Phần tử null | Constructor NONNULL từ chối hoặc xử lý theo chính sách |
| Comparator khác natural | `getComparator` trả đúng comparator hoặc từ chối SORTED |
| Nguồn bị thay đổi | Snapshot vẫn không bị sai dữ liệu đã công bố |
| Chạy song song | Kết quả terminal theo hợp đồng, không phụ thuộc thứ tự thread |
| Flags | Cả nguồn gốc và phần tách đều có các cờ thực sự đúng |
| Kích thước | Nếu SIZED/SUBSIZED, số còn lại khớp `estimateSize` |
| Thao tác downstream | `distinct`, `sorted`, `limit`, `toList` trả kết quả đúng |

### 17.1. Đoạn test độc lập với framework kiểm thử

Các phương thức sau đặt bên trong lớp `SortedUniqueSpliteratorDemo` của mục 10:

~~~java
static void expectInvalid(List<Integer> values) {
    try {
        new SortedUniqueIntegers(values);
        throw new AssertionError("Đáng lẽ nguồn không hợp lệ: " + values);
    } catch (IllegalArgumentException | NullPointerException expected) {
        // PASS: constructor từ chối nguồn sai hợp đồng.
    }
}

static void verifySource() {
    List<Integer> expected = List.of(1, 2, 5, 8, 13, 21);

    SortedUniqueIntegers sp = new SortedUniqueIntegers(expected);

    int required = Spliterator.ORDERED
            | Spliterator.DISTINCT
            | Spliterator.SORTED
            | Spliterator.NONNULL
            | Spliterator.SIZED
            | Spliterator.SUBSIZED;

    if (!sp.hasCharacteristics(required)) {
        throw new AssertionError("Thiếu characteristic cần thiết");
    }

    if (sp.getComparator() != null) {
        throw new AssertionError("Nguồn phải dùng natural order");
    }

    Spliterator<Integer> prefix = sp.trySplit();
    if (prefix == null || !prefix.hasCharacteristics(required)) {
        throw new AssertionError("Phân chia không đúng hợp đồng");
    }

    List<Integer> left = StreamSupport.stream(prefix, false).toList();
    List<Integer> right = StreamSupport.stream(sp, false).toList();

    java.util.ArrayList<Integer> recombined =
            new java.util.ArrayList<>(left);
    recombined.addAll(right);

    if (!recombined.equals(expected)) {
        throw new AssertionError("Mất, nhân đôi hoặc đảo phần tử");
    }

    List<Integer> parallel = StreamSupport.stream(
            new SortedUniqueIntegers(expected), true
    ).toList();

    if (!parallel.equals(expected)) {
        throw new AssertionError("Kết quả parallel không khớp");
    }

    expectInvalid(List.of(1, 1, 2)); // DISTINCT bị vi phạm.
    expectInvalid(List.of(3, 2, 4)); // SORTED bị vi phạm.
    expectInvalid(java.util.Arrays.asList(1, null, 3)); // NONNULL.

    System.out.println("SPLITERATOR_OK");
}
~~~

Gọi `verifySource()` từ `main` hoặc một unit test. Nên bổ sung bộ thử với nhiều độ dài và đường chia khác nhau, đặc biệt nếu Spliterator có thuật toán phân chia phức tạp hơn một lát mảng.

**Không chỉ tin vào `hasCharacteristics`.** Trong test, cần so dữ liệu được phát thật với một oracle độc lập từ snapshot đã xác thực.

### 17.2. Kiểm tra từng phần tử của toàn bộ kết quả

~~~java
List<Integer> result = StreamSupport.stream(
        new SortedUniqueIntegers(List.of(1, 2, 3, 5, 8)),
        true
).toList();

for (int i = 0; i < result.size(); i++) {
    if (result.get(i) == null) {
        throw new AssertionError("Vi phạm NONNULL");
    }

    if (i > 0 && result.get(i - 1) >= result.get(i)) {
        throw new AssertionError("Không tăng nghiêm ngặt");
    }
}
~~~

Kiểm tra tăng nghiêm ngặt phù hợp với **nguồn Integer được thiết kế riêng** trong bài. Với nguồn có comparator hoặc các giá trị khác, thay điều kiện bằng một phép kiểm đúng theo comparator và kiểm tra DISTINCT qua `equals`.

---

## 18. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| Khai báo `ORDERED` vì lần chạy thử thấy thứ tự ổn định | Thứ tự tình cờ không phải encounter order được định nghĩa | Kiểm tra nguồn và thuật toán `trySplit` |
| Nghĩ `ORDERED` có nghĩa tăng dần | Thứ tự List có thể là `[9,1,5]` | Dùng `SORTED` chỉ khi thật sự đã sắp xếp |
| Nghĩ `DISTINCT` nghĩa khóa `id` duy nhất | `equals` có thể dựa vào nhiều trường | Xác định quy tắc trùng theo `equals` riêng với unique business key |
| Khai báo `SORTED` nhưng thiếu `ORDERED` | Vi phạm quan hệ SORTED kéo theo ORDERED | Công bố cả hai và bảo đảm thứ tự duyệt |
| Không override `getComparator` cho custom SORTED | Hàm mặc định có thể ném `IllegalStateException` | Trả null cho natural order, comparator phù hợp cho custom order |
| Khai báo `SORTED` khi chỉ một prefix đã sắp xếp | Các phần còn lại vẫn có thể đảo | Xác thực toàn bộ dữ liệu, hoặc không công bố SORTED |
| Khai báo `DISTINCT` khi nguồn chứa hai giá trị equals nhau | `distinct` có thể được tối ưu trên giả định sai | Khử trùng trước hoặc bỏ cờ |
| Khai báo `NONNULL` nhưng mapper/iterator có thể trả null | Vi phạm lời cam kết của nguồn | Kiểm tra null hoặc không công bố NONNULL |
| `trySplit` lấy các phần tử đan xen từ nguồn ORDERED | Phần tách không còn là tiền tố | Tách theo lát liên tiếp |
| Dùng lại Spliterator đã duyệt | Trạng thái cursor đã thay đổi | Tạo nguồn mới cho mỗi pipeline |
| Cho nguồn mutable thay đổi trong lúc duyệt | Có thể làm sai flags và phép duyệt | Snapshot, đồng bộ hoặc nguồn concurrent đúng hợp đồng |
| Dựa vào `forEach` song song để in theo ORDERED | Thứ tự chạy giữa thread không bảo đảm | `forEachOrdered` khi cần thứ tự |
| Coi flags của source là flags của mọi pipeline | `map`/`filter`/`unordered` có thể đổi thông tin | Đánh giá hợp đồng từng thao tác |
| Tự thêm `SIZED` để tăng tốc | Kích thước sai có thể ảnh hưởng tối ưu | Chỉ khai báo nếu `estimateSize` thật sự chính xác |

---

## 19. Quy trình thiết kế một Spliterator có characteristics đúng

Một checklist áp dụng trước khi xuất bản nguồn tùy chỉnh:

1. **Định nghĩa tập giá trị:** kiểu `T` là gì, nguồn có null không, phần tử nào có thể trùng?
2. **Định nghĩa encounter order:** thứ tự theo vị trí, thời gian hay comparator? Có cần bảo toàn khi chạy song song?
3. **Xác định DISTINCT:** dùng `equals` chứ không suy từ duy nhất của một trường ngoài định nghĩa `equals`.
4. **Xác định SORTED:** chọn natural ordering hoặc comparator; nếu công bố SORTED phải công bố ORDERED và `getComparator` đúng.
5. **Xác định NONNULL:** mọi đường phát dữ liệu và các thay đổi nguồn có bảo đảm không phát null không?
6. **Thiết kế tryAdvance:** phát đúng một phần tử cho mỗi lần gọi thành công, không vượt ranh giới dữ liệu, kiểm tra action không null.
7. **Thiết kế trySplit:** với ORDERED, trả tiền tố; bảo đảm không mất/nhân đôi và mọi phân vùng vẫn tuân theo các cờ.
8. **Công bố SIZED/SUBSIZED nếu thực sự biết kích thước:** `estimateSize` phải phản ánh phần còn lại sau khi tách/duyệt.
9. **Quản lý vòng đời nguồn:** nếu nguồn có tài nguyên I/O, đóng đúng cách; Spliterator không tự biến tài nguyên thành an toàn.
10. **Kiểm chứng:** dữ liệu rỗng, một phần tử, dữ liệu trùng, chưa sắp, null, chia nhiều cấp, chạy tuần tự/song song, downstream `distinct` và `sorted`.
11. **Đo hiệu năng sau khi đúng:** thêm cờ không bảo đảm Stream nhanh hơn; dùng benchmark với dữ liệu và JDK thực tế.

Quy trình tóm tắt:

~~~text
Có dữ liệu nguồn
       |
       v
Xác định tính chất bảo đảm
       |
       +--- không chắc chắn? ---> Không công bố cờ đó
       |
       v
Xác thực / snapshot khi phù hợp
       |
       v
Cài đặt tryAdvance + trySplit
       |
       v
Khai báo đúng characteristics + getComparator
       |
       v
Kiểm thử nguồn và mọi phần sau khi tách
       |
       v
Tạo Stream qua StreamSupport
       |
       v
Đo lường / tối ưu sau khi đã đúng
~~~

---

## 20. Bài tập tự kiểm tra (kèm đáp án)

### Bài 1. ORDERED khác SORTED thế nào?

**Đề:** Nguồn `List.of(9, 1, 5)` duyệt theo thứ tự phần tử của List. Có ORDERED không? Có SORTED không?

**Đáp án:** Nguồn List có encounter order `9, 1, 5` nên có thể công bố ORDERED; không được công bố SORTED tăng dần vì dữ liệu chưa được sắp xếp. ORDERED không đồng nghĩa SORTED.

### Bài 2. DISTINCT và khóa nghiệp vụ

**Đề:** Hai record `Product(1, "BOOK")` và `Product(2, "BOOK")` khác nhau theo `equals`. Nếu nguồn không chứa record trùng, có thể DISTINCT không? Điều đó có chứng minh category duy nhất không?

**Đáp án:** Có thể bảo đảm DISTINCT đối với **phần tử Product** nếu mọi cặp phần tử khác nhau theo `equals`. Nhưng category không duy nhất vì hai record đều có `"BOOK"`. Nếu cần Map theo category một-một, vẫn phải có chính sách xử lý khóa trùng hoặc dùng `groupingBy`.

### Bài 3. SORTED có thể thiếu ORDERED không?

**Đề:** Một Spliterator công bố `SORTED` nhưng không công bố `ORDERED` có đúng hợp đồng không?

**Đáp án:** Không. `SORTED` kéo theo `ORDERED`. Một nguồn tùy chỉnh phải bảo đảm thứ tự duyệt và khai báo đúng các cờ; `getComparator()` phải phản ánh thứ tự sắp xếp.

### Bài 4. getComparator trả null khi nào?

**Đề:** Với một Spliterator đã có `SORTED` theo natural order của `Integer`, `getComparator()` trả gì?

**Đáp án:** Trả `null`. Nếu nguồn SORTED theo comparator riêng thì trả comparator ấy. Nếu không có SORTED, `getComparator()` phải ném `IllegalStateException`.

### Bài 5. Dãy [1, 1, 2, 3]

**Đề:** Dãy được duyệt tăng dần `[1, 1, 2, 3]`, không null. Những đặc tính nào trong bốn cờ có thể đúng?

**Đáp án:** `ORDERED`, `SORTED` và `NONNULL` nếu nguồn bảo đảm chúng; **không có `DISTINCT`**, vì số `1` xuất hiện hai lần. Nếu nguồn thực tế là một List thông thường, đừng tự mặc định List công bố `SORTED` dù dữ liệu hiện đang sắp.

### Bài 6. trySplit của nguồn ORDERED

**Đề:** Nguồn còn lại `[A, B, C, D]`, `trySplit` trả phần `[B, D]` và giữ `[A, C]`. Có hợp lệ nếu nguồn công bố ORDERED không?

**Đáp án:** Không. Phần trả lại phải là **tiền tố** của phần còn lại. Một cách hợp lệ là trả `[A, B]` và giữ `[C, D]`.

### Bài 7. NONNULL có chứng minh email hợp lệ không?

**Đề:** Stream các đối tượng `Customer` đều khác null, nhưng một số customer có email rỗng. Cờ NONNULL có phát hiện email rỗng không?

**Đáp án:** Không. NONNULL chỉ nói phần tử `Customer` không phải `null`; nó không kiểm tra giá trị field hoặc quy tắc dữ liệu nghiệp vụ.

### Bài 8. Cờ DISTINCT bị khai báo sai

**Đề:** Nguồn tùy chỉnh phát `[2, 2, 3]` nhưng khai báo `DISTINCT`. Vì sao nguy hiểm nếu pipeline có `distinct()`?

**Đáp án:** Framework có quyền tin vào cờ DISTINCT và bỏ công việc loại trùng khi tối ưu. Kết quả có thể còn số `2` trùng. Phải bỏ cờ hoặc khử trùng ở nguồn trước khi công bố.

### Bài 9. Kiểm tra custom SORTED với comparator

**Đề:** Một nguồn String đã sắp theo `Comparator.reverseOrder()`. `getComparator()` nên trả gì?

**Đáp án:** Trả comparator phản ánh thứ tự đảo ấy; không trả `null` vì `null` chỉ có nghĩa natural order. Nguồn còn phải công bố ORDERED và thực sự duyệt theo thứ tự đảo đã nói.

### Bài 10. map có giữ NONNULL không?

**Đề:** Nguồn `List<Integer>` không có null, sau đó `map(n -> n > 10 ? "big" : null)`. Có được tự công bố NONNULL cho kết quả không?

**Đáp án:** Không. Hàm `map` có thể tạo `null`. Việc nguồn đầu vào không chứa null không đủ bảo đảm nguồn đầu ra không chứa null.

### Bài 11. SIZED và SUBSIZED

**Đề:** Một Spliterator có `estimateSize() == 10` lúc đầu nhưng sau `trySplit` không biết chính xác kích thước hai phần. Có nên khai báo `SUBSIZED` không?

**Đáp án:** Không. `SUBSIZED` yêu cầu những Spliterator phát sinh qua chia đều đáp ứng hợp đồng kích thước chính xác. Chỉ khai báo khi cách phân chia bảo đảm được điều đó.

### Bài 12. Kiểm tra nguồn song song

**Đề:** Vì sao chỉ so `sequential.equals(parallel)` chưa đủ để khẳng định bốn cờ được khai báo đúng?

**Đáp án:** Hai chế độ có thể cùng bỏ sót một lỗi, cùng nhận cờ sai hoặc dữ liệu thử chưa kích hoạt trường hợp biên. Cần kiểm tra **trực tiếp** tập cờ, dữ liệu phát ra, đặc tính null/trùng/sắp xếp, cách tách tiền tố/hậu tố, kích thước và các trường hợp nguồn không hợp lệ.

---

**Ghi nhớ:** `ORDERED` là **thứ tự gặp phần tử**, `DISTINCT` là **không trùng theo `equals`**, `SORTED` là **được sắp theo natural order/comparator** (và bắt buộc ORDERED), còn `NONNULL` là **không phát phần tử null**. Các cờ này là **hợp đồng của Spliterator**, không phải lời đoán từ một bộ dữ liệu mẫu. Khi tự viết nguồn cho Java Stream API, hãy xác thực dữ liệu, cài đặt `trySplit` đúng với encounter order, công bố `getComparator` phù hợp và kiểm thử cả nguồn gốc lẫn các phần sau khi tách — nhất là trước khi dùng Stream song song.

