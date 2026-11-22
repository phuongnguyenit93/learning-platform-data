# Comparator không nhất quán với `equals()` và hợp đồng `Set` hoặc `Map`

## 1. Vấn đề cốt lõi: hai cách định nghĩa “cùng một phần tử”

Trong Java, `TreeSet<E>` và `TreeMap<K,V>` là các cấu trúc có thứ tự. Chúng dùng **thứ tự tự nhiên** (`Comparable.compareTo`) hoặc **thứ tự do `Comparator.compare` chỉ định** để tìm kiếm và phân biệt các phần tử/khóa. Với hai giá trị `a` và `b`, chúng xem là **tương đương theo thứ tự** khi:

```java
comparator.compare(a, b) == 0
```

Đây là điều kiện dùng để xác định một vị trí tương đương trong cây; nó **không nhất thiết giống** `a.equals(b)`. Trong khi đó, giao diện `Set` và `Map` định nghĩa sự bằng nhau của phần tử và khóa theo hợp đồng `equals` (với cách xử lý `null` phù hợp):

- `Set` không được chứa hai phần tử bằng nhau theo `equals`.
- `Map` có mỗi khóa là duy nhất theo `equals`; ghi thêm cùng khóa logic sẽ thay thế giá trị của khóa ấy.
- `TreeSet` và `TreeMap` dùng kết quả so sánh bằng 0 để ra quyết định tương đương, vì vậy nếu `Comparator` không nhất quán với `equals`, hành vi trong cây có thể **không đáp ứng được hợp đồng chung của `Set` hoặc `Map`**.

Một bộ so sánh gọi là **nhất quán với `equals`** khi, đối với mọi cặp phần tử hợp lệ trong miền so sánh:

```text
comparator.compare(a, b) == 0    ⇔    a.equals(b) == true
```

Ký hiệu `⇔` là “khi và chỉ khi”: **hai chiều đều phải đúng**. Cần phân biệt điều này với yêu cầu cơ bản của một bộ so sánh là giữ thứ tự nhất quán (dấu đảo chiều, bắc cầu, và tương đương theo thứ tự ứng xử nhất quán với phần tử thứ ba). Một `Comparator` vẫn có thể xác định một thứ tự nội tại hợp lệ nhưng **không nhất quán với `equals`**; vấn đề lộ ra khi dùng nó làm quy tắc duy nhất của `TreeSet` hoặc `TreeMap`.

Theo tài liệu Java, cấu trúc cây vẫn có hành vi được xác định theo comparator ngay cả khi thứ tự không nhất quán với `equals`; tuy nhiên khi đó chúng có thể **vi phạm hợp đồng tổng quát của `Set` hoặc `Map`**. Đây là vấn đề về ngữ nghĩa API, không nhất thiết là ngoại lệ lúc chạy.

## 2. Hai dạng không nhất quán cần phân biệt

### Dạng A: `compare(a, b) == 0` nhưng `!a.equals(b)`

Ví dụ: hai chuỗi `"cat"` và `"dog"` có cùng độ dài, nhưng nội dung khác nhau. Một `Comparator` chỉ so độ dài:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
System.out.println(byLength.compare("cat", "dog")); // 0
System.out.println("cat".equals("dog"));            // false
```

Đây là đoạn minh họa khi đặt trong một phương thức và import `java.util.Comparator`. Với `TreeSet` dùng `byLength`, chuỗi thứ hai không được thêm thành phần tử mới vì comparator cho kết quả 0. Tập có thể có kích thước 1 dù `equals` coi hai chuỗi là khác nhau; `contains("dog")` có thể là `true` mặc dù tập thực tế giữ chuỗi `"cat"`.

Với `TreeMap` dùng cùng comparator, `put("dog", value2)` có thể **ghi đè giá trị** gắn với khóa `"cat"`, vì bản đồ xem hai khóa có cùng thứ tự. Đối tượng khóa đã được lưu thường vẫn là khóa ban đầu, còn giá trị được cập nhật.

Về mặt hợp đồng `Set` và `Map`, đây là sự **gộp nhầm các giá trị khác nhau**.

### Dạng B: `a.equals(b)` là `true` nhưng `compare(a, b) != 0`

Giả sử lớp `Ticket` định nghĩa danh tính theo `id`, nhưng comparator lại ưu tiên `priority` trước `id`. Hai vé có cùng `id="T7"` nhưng priority khác nhau được `equals` coi là cùng vé, còn comparator lại phân biệt.

`TreeSet` có thể giữ **cả hai vé bằng nhau theo `equals`** vì phép so sánh của cây không trả 0. `TreeMap` cũng có thể chứa hai entry có khóa `equals` bằng nhau, trái với kỳ vọng từ giao diện `Map`. Một `HashSet` hoặc `HashMap` với `equals`/`hashCode` đúng lại xem chúng là cùng phần tử/khóa.

Đây là chiều ngược lại của lỗi: **tách nhầm một giá trị logic thành nhiều mục**.

| Điều kiện của cặp `a,b` | Theo `equals` | Theo comparator | Hậu quả có thể gặp trong cấu trúc cây |
| --- | --- | --- | --- |
| `compare(a,b)==0`, `!a.equals(b)` | Khác nhau | Tương đương | `TreeSet` bỏ qua một phần tử, `TreeMap` thay giá trị của khóa khác |
| `a.equals(b)`, `compare(a,b)!=0` | Bằng nhau | Khác vị trí | `TreeSet` giữ hai phần tử bằng nhau, `TreeMap` giữ hai khóa bằng nhau |
| `a.equals(b)`, `compare(a,b)==0` | Bằng nhau | Tương đương | Hai cơ chế đồng thuận |
| `!a.equals(b)`, `compare(a,b)!=0` | Khác nhau | Khác vị trí | Hai cơ chế đồng thuận |

Bảng trên giả định comparator vẫn tuân thủ **hợp đồng thứ tự** và khóa không thay đổi trong khi nằm trong cây. Một comparator vi phạm bắc cầu hoặc đổi kết quả tùy thời điểm có thể gây những vấn đề nghiêm trọng khác, nằm ngoài sự không nhất quán với `equals`.

## 3. Chương trình Java 17+ minh họa cả hai lỗi và cách sửa

Lưu toàn bộ mã sau thành **`ComparatorContractDemo.java`**. Nó dùng `record Word` (bình đẳng theo chuỗi `text`) và `Ticket` (bình đẳng theo `id`). Phần đầu chỉ so độ dài; phần sau dùng thứ tự theo priority trái với danh tính vé.

```java
import java.util.*;

public class ComparatorContractDemo {
    record Word(String text) {}

    static final class Ticket {
        private final String id;
        private final int priority;

        Ticket(String id, int priority) {
            this.id = Objects.requireNonNull(id);
            this.priority = priority;
        }

        String id() {
            return id;
        }

        int priority() {
            return priority;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Ticket t && id.equals(t.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Word cat = new Word("cat");
        Word dog = new Word("dog");
        Comparator<Word> byLength =
                Comparator.comparingInt(w -> w.text().length());

        TreeSet<Word> byLengthSet = new TreeSet<>(byLength);
        boolean first = byLengthSet.add(cat);
        boolean second = byLengthSet.add(dog);

        System.out.println("words equals = " + cat.equals(dog));
        System.out.println("words compare = " + byLength.compare(cat, dog));
        System.out.println("tree set add = " + first + ", " + second);
        System.out.println("tree set size = " + byLengthSet.size());
        System.out.println("tree set contains dog = "
                + byLengthSet.contains(dog));
        System.out.println("hash set size = "
                + new HashSet<>(List.of(cat, dog)).size());

        TreeMap<Word, String> wordMap = new TreeMap<>(byLength);
        wordMap.put(cat, "first");
        String previous = wordMap.put(dog, "second");

        System.out.println("tree map previous = " + previous);
        System.out.println("tree map size = " + wordMap.size());
        System.out.println("tree map get dog = " + wordMap.get(dog));
        System.out.println("tree map stored key = " + wordMap.firstKey());

        Comparator<Word> byLengthThenText =
                byLength.thenComparing(Word::text);
        TreeSet<Word> fixedWords = new TreeSet<>(byLengthThenText);
        fixedWords.add(cat);
        fixedWords.add(dog);
        System.out.println("fixed words size = " + fixedWords.size());

        Ticket low = new Ticket("T7", 1);
        Ticket high = new Ticket("T7", 9);
        Comparator<Ticket> byPriorityThenId =
                Comparator.comparingInt(Ticket::priority)
                          .thenComparing(Ticket::id);

        TreeSet<Ticket> ticketSet = new TreeSet<>(byPriorityThenId);
        ticketSet.add(low);
        ticketSet.add(high);

        TreeMap<Ticket, String> ticketMap =
                new TreeMap<>(byPriorityThenId);
        ticketMap.put(low, "low");
        ticketMap.put(high, "high");

        System.out.println("tickets equals = " + low.equals(high));
        System.out.println("tickets compare = "
                + byPriorityThenId.compare(low, high));
        System.out.println("ticket tree set size = " + ticketSet.size());
        System.out.println("ticket hash set size = "
                + new HashSet<>(List.of(low, high)).size());
        System.out.println("ticket tree map size = " + ticketMap.size());

        TreeSet<Ticket> fixedTickets =
                new TreeSet<>(Comparator.comparing(Ticket::id));
        fixedTickets.add(low);
        fixedTickets.add(high);
        System.out.println("fixed tickets size = " + fixedTickets.size());
    }
}
```

Trong thư mục chứa tệp, biên dịch và chạy:

```bash
javac ComparatorContractDemo.java
java ComparatorContractDemo
```

Đầu ra của chương trình:

```text
words equals = false
words compare = 0
tree set add = true, false
tree set size = 1
tree set contains dog = true
hash set size = 2
tree map previous = first
tree map size = 1
tree map get dog = second
tree map stored key = Word[text=cat]
fixed words size = 2
tickets equals = true
tickets compare = -1
ticket tree set size = 2
ticket hash set size = 1
ticket tree map size = 2
fixed tickets size = 1
```

### Diễn giải kết quả đầu tiên: comparator gộp nhầm

- `cat.equals(dog)` trả `false` vì `Word` là `record`, so thành phần `text`; `"cat"` và `"dog"` khác nhau.
- `byLength.compare(cat,dog)` trả `0` vì cả hai có độ dài 3.
- `byLengthSet.add(cat)` trả `true`; `add(dog)` trả `false` vì cây xem `dog` tương đương với `cat` đã có. Kích thước cuối là 1.
- `byLengthSet.contains(dog)` là `true` theo cách tìm kiếm của cây, mặc dù phần tử được lưu là `cat`. Tương phản, `HashSet` dựa vào `equals`/`hashCode` của `Word` nên có kích thước 2.
- `wordMap.put(dog,"second")` trả giá trị trước đó `"first"`; kích thước vẫn 1 và `get(dog)` là `"second"`. Đối tượng khóa trong entry là `Word[text=cat]`, cho thấy **giá trị mới thay thế theo comparator, nhưng không tự biến khóa cũ thành khóa mới**.

Đây là điểm dễ nhầm: `contains`, `get` và `put` của cây tuân theo comparator đã cung cấp. Chúng không thực hiện bước kiểm tra cuối `equals` để chữa trường hợp comparator trả 0 sai với danh tính logic.

### Diễn giải kết quả thứ hai: comparator tách nhầm

- `low.equals(high)` là `true` vì `Ticket.equals` chỉ dựa trên `id="T7"`; `hashCode` cũng dùng `id` nên hợp đồng hash được giữ.
- `byPriorityThenId.compare(low,high)` trả `-1` vì priority 1 nhỏ hơn 9, dù cùng `id`.
- `TreeSet` và `TreeMap` vẫn giữ 2 mục vì comparator coi chúng khác nhau. `HashSet` coi chúng là một giá trị logic, nên kích thước 1.
- `Comparator.comparing(Ticket::id)` chỉ so `id`; hai vé cùng `id` sẽ có kết quả 0, nên `fixedTickets` có kích thước 1, khớp chính sách equality của `Ticket`.

Hai tình huống này minh họa **cả hai hướng cần kiểm tra** khi yêu cầu comparator nhất quán với `equals`.

## 4. Hợp đồng `Set` và `Map` bị ảnh hưởng cụ thể thế nào?

### 4.1. `Set`: thêm, tìm kiếm, xóa và duy nhất

Giao diện `Set` xác định một tập các phần tử **không trùng nhau theo `equals`**. Về bản chất, `add(e)` trả về `false` nếu tập đã chứa phần tử bằng `e`; `contains(o)` có nghĩa tìm sự hiện diện của phần tử bằng `o`.

Với `TreeSet`, cây sử dụng comparator để xác định xem phần tử có tương đương với mục đã có không:

- Nếu `compare(a,b)==0` nhưng `!a.equals(b)`, việc thêm `b` sau `a` có thể bị từ chối; `contains(b)` có thể trả `true` dù `b` khác mọi đối tượng hiện đang lưu theo `equals`.
- `remove(b)` cũng có thể xóa mục đại diện `a` nếu `compare(a,b)==0`, vì mục tiêu tìm kiếm được xác định bằng thứ tự.
- Nếu `a.equals(b)` nhưng `compare(a,b)!=0`, tập có thể chứa cả hai phần tử, phá kỳ vọng không trùng nhau.

Với `HashSet`, điều kiện bằng nhau được xây dựng trên `equals` và `hashCode`; comparator không được dùng. Sự khác biệt giữa `HashSet` và `TreeSet` trong ví dụ là kết quả trực tiếp của hai quy tắc định danh.

### 4.2. `Map`: khóa tương đương bị thay hoặc giữ trùng

Giao diện `Map` định nghĩa khóa duy nhất theo `equals`. Với `HashMap`, hai khóa bằng nhau theo `equals` và có hash tương thích đại diện cùng một mapping.

`TreeMap` cần một thứ tự để định vị khóa, nên dùng `compare(k1,k2)==0`:

- Khi comparator trả 0 cho hai khóa khác nhau theo `equals`, `put(k2,v2)` có thể cập nhật entry của `k1`. Giá trị trước đó bị thay; `size()` không tăng. `get(k2)` tìm thấy entry bằng quy tắc của comparator.
- Khi comparator trả khác 0 cho hai khóa bằng nhau theo `equals`, `TreeMap` có thể giữ cả hai entry. Khi đó phép tra cứu bằng một đối tượng thứ ba bằng các khóa theo `equals` có thể phụ thuộc kết quả comparator và không khớp với kỳ vọng của giao diện `Map`.
- Các view `keySet()`, `entrySet()` và các thao tác thứ tự như `firstKey()`, `subMap()`, `headMap()`, `tailMap()` phụ thuộc vào quan hệ thứ tự, nên phạm vi dữ liệu cũng có thể khác trực giác nếu người dùng nghĩ “bằng khóa” có nghĩa `equals`.

**Lưu ý quan trọng:** Đây là lỗi ở **chính sách định nghĩa khóa** hoặc cách dùng cấu trúc, không nhất thiết là lỗi triển khai nội bộ của `TreeMap`. Nếu ứng dụng cố ý dùng đồng nhất theo comparator (ví dụ chuỗi không phân biệt hoa thường), kết quả có thể phù hợp yêu cầu nghiệp vụ, nhưng cần hiểu nó **khác ngữ nghĩa `equals` của kiểu khóa** và có thể phá hợp đồng `Map` tổng quát.

### 4.3. Vì sao “chỉ cần comparator sắp xếp đúng” vẫn chưa đủ?

Một comparator so theo độ dài có thể giữ hoàn toàn các quy tắc của thứ tự: dấu đảo chiều, bắc cầu, các chuỗi cùng độ dài ứng xử giống nhau khi so với chuỗi thứ ba. Nó **đúng như một phép sắp xếp theo độ dài**, nhưng không phù hợp nếu `TreeSet` phải chứa mọi chuỗi khác nội dung.

Ngược lại, comparator theo priority rồi id cũng có thể là một thứ tự hợp lệ, nhưng không phù hợp khi `Ticket.equals` định nghĩa hai vé cùng id là cùng một vé.

Do đó, cần tách hai câu hỏi: **(1) Bộ so sánh có tuân thủ hợp đồng `Comparator` không? (2) Kết quả 0 có đại diện đúng equality của khóa/phần tử trong cấu trúc cây không?**

## 5. Cách sửa: thiết kế tiêu chí so sánh theo danh tính logic

### 5.1. Thêm tie-breaker cho những đối tượng `equals` khác nhau

Nếu `Word.equals` coi toàn bộ `text` là danh tính, đừng chỉ so chiều dài. Tạo comparator theo **độ dài trước, nội dung sau**:

```java
Comparator<Word> byLengthThenText =
        Comparator.comparingInt((Word w) -> w.text().length())
                  .thenComparing(Word::text);
```

Đây là một biểu thức minh họa trong ngữ cảnh có `Word`, cần `import java.util.Comparator`. Nó trả về 0 **chỉ khi** cả độ dài và nội dung bằng nhau; vì nội dung giống nhau tất yếu cùng độ dài, phép so sánh 0 tương đương với `Word.equals` trong ví dụ.

`TreeSet` vẫn sắp xếp theo độ dài tăng dần. Khi bằng độ dài, nó phân biệt `"cat"` và `"dog"` theo thứ tự từ điển. Kết quả đúng là cả hai cùng được giữ.

Không nên dùng các tie-breaker tùy tiện như `System.identityHashCode` để “ép khác nhau”: identity hash vẫn có thể va chạm, và hai đối tượng bằng nhau theo giá trị lại có thể bị so thành khác. Tie-breaker phải phù hợp với **chính sách equality**, không phải tìm một số ngẫu nhiên để tránh kết quả 0.

### 5.2. Loại trường ngoài danh tính khỏi comparator dùng cho cây

Trong `Ticket`, `equals` chỉ dựa trên `id`. Muốn dùng `TreeSet<Ticket>` như một `Set` theo danh tính vé, comparator phải cho 0 khi id bằng nhau:

```java
Comparator<Ticket> byId = Comparator.comparing(Ticket::id);
```

Đây là dòng minh họa trong ngữ cảnh đã định nghĩa lớp `Ticket` với getter `id()`. Khi `low` và `high` có cùng id, bộ so sánh cho 0, thống nhất với `equals`. Vì `id` là chuỗi không null và tham gia duy nhất vào `equals`, comparator này còn phân biệt mọi giá trị id khác nhau.

Nếu yêu cầu **hiển thị** vé theo `priority` nhưng vẫn muốn định danh theo id, không nên buộc `TreeSet` vừa sắp theo priority vừa phải coi cùng id là trùng khi priority khác. Có thể lưu vé theo id bằng `Map<String,Ticket>`, rồi tạo danh sách và sắp xếp bản trình bày bằng comparator priority. Quy tắc tập hợp/khóa và quy tắc hiển thị lúc đó có thể khác nhau mà không gây nhập nhằng.

### 5.3. Có nên sửa `equals` để khớp comparator?

Có thể sửa `equals` **chỉ khi yêu cầu nghiệp vụ thật sự thay đổi định nghĩa danh tính**. Ví dụ, nếu một vé có id và phiên bản, muốn hai vé cùng id nhưng phiên bản khác nhau là hai giá trị riêng, có thể để cả `equals`, `hashCode` và comparator xem phiên bản là thành phần danh tính.

Không nên sửa `equals` chỉ để chữa một comparator dùng cho màn hình sắp xếp: thay đổi `equals` còn ảnh hưởng tới `HashSet`, `HashMap`, caching, deduplication và toàn bộ mã dựa vào giá trị logic của kiểu đó.

## 6. Khi nào chủ động chấp nhận comparator không nhất quán với `equals`?

### Sắp xếp danh sách thông thường

Khi `List.sort(comparator)` hoặc `Collections.sort(list,comparator)`, hai đối tượng có kết quả so sánh 0 có thể cùng xuất hiện trong danh sách. Sắp xếp không có hợp đồng “mỗi giá trị chỉ xuất hiện một lần” như `Set`. Vì vậy, **comparator chỉ theo độ dài** hoàn toàn có thể phù hợp khi cần nhóm các chuỗi theo chiều dài trong một `List`.

Điều kiện vẫn là comparator phải tạo một thứ tự nhất quán theo hợp đồng so sánh. Sắp xếp không tự sửa được comparator có vòng lặp hay thiếu tính bắc cầu.

### Muốn cố ý coi khóa khác `equals` là cùng khóa

Ví dụ, một ứng dụng xem `"Admin"` và `"admin"` là cùng tên người dùng khi xử lý trong một `TreeMap<String,V>` với `String.CASE_INSENSITIVE_ORDER`. Đây có thể là lựa chọn có chủ đích, nhưng `String.equals` vẫn phân biệt chữ hoa và thường. Khi giao tiếp với các API khác sử dụng `HashMap`/`HashSet`, kết quả gộp và nhận diện có thể khác nhau.

Nếu định danh theo chữ thường là quy tắc chính của nghiệp vụ, thường dễ kiểm soát hơn khi **chuẩn hóa khóa trước khi lưu** (với chính sách locale/Unicode phù hợp) hoặc thiết kế một kiểu khóa có `equals`, `hashCode` và comparator cùng mô tả chính sách. Tránh đổi ý nghĩa equality ngầm giữa các collection khác nhau.

### `Comparable` và `BigDecimal`

Vấn đề tương tự cũng xảy ra với **thứ tự tự nhiên** do `compareTo` cung cấp mà không cần comparator riêng. Chẳng hạn:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");
System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

Đoạn này cần `import java.math.BigDecimal` và đặt trong một phương thức. `BigDecimal.compareTo` so giá trị số; `BigDecimal.equals` còn xét `scale`. `TreeSet<BigDecimal>` coi hai giá trị này tương đương theo thứ tự, còn `HashSet<BigDecimal>` có thể giữ cả hai. Đây là một ngoại lệ quen thuộc giúp thấy yêu cầu **nhất quán với `equals` là rất quan trọng với cấu trúc cây**.

## 7. Kiểm thử và rà soát bộ so sánh cho tập/bản đồ có thứ tự

Không chỉ kiểm tra danh sách được sắp đẹp mắt. Với mọi kiểu khóa/phần tử muốn đưa vào `TreeSet` hoặc `TreeMap`, hãy kiểm tra **hai chiều tương thích**:

```java
boolean sameByEquals = Objects.equals(a, b);
boolean sameByComparator = comparator.compare(a, b) == 0;

if (sameByEquals != sameByComparator) {
    throw new AssertionError("Comparator inconsistent with equals");
}
```

Đây là **đoạn kiểm thử** có các biến `a`, `b` và `comparator` được chuẩn bị trước; không phải chương trình chạy độc lập. Phải thử các cặp cùng giá trị, khác giá trị, cùng khóa chính nhưng khác trường phụ, khác khóa chính nhưng cùng trường sắp xếp, và giá trị biên. Đồng thời xác minh comparator có thể so sánh các đối tượng trong miền mà collection hỗ trợ.

Ngoài consistency-with-equals, hãy kiểm tra đầy đủ hợp đồng thứ tự:

1. **Dấu đảo chiều:** `Integer.signum(compare(a,b)) == -Integer.signum(compare(b,a))`. So **dấu**, không so `compare(a,b) == -compare(b,a)` vì phủ định `Integer.MIN_VALUE` có thể tràn.
2. **Bắc cầu:** nếu `compare(a,b) > 0` và `compare(b,c) > 0` thì `compare(a,c) > 0`.
3. **Nhất quán của tương đương theo thứ tự:** nếu `compare(a,b) == 0` thì dấu của `compare(a,c)` phải giống dấu của `compare(b,c)` với mọi `c` có thể so sánh.
4. **Tính ổn định:** khóa không được đổi trường tham gia so sánh khi đang được lưu trong cây. Nếu thay khóa, cần xóa entry cũ rồi thêm lại hoặc xây lại cấu trúc.
5. **Tương thích với equality:** đối với `Set`/`Map` theo danh tính logic, kiểm tra `compare(a,b)==0` khi và chỉ khi `a.equals(b)`.

Có thể viết một bộ kiểm thử nhỏ để chèn cả các cặp vào `TreeSet` lẫn `HashSet`, kiểm tra kích thước, `contains` và `remove`; và chèn vào `TreeMap`, kiểm tra `put` trả giá trị trước đó, `size`, `get`, `firstKey`. Khi mục tiêu là dùng `TreeSet`/`TreeMap` đúng hợp đồng chung, kết quả của bộ kiểm thử phải phản ánh **cùng một chính sách bình đẳng**.

Một phép kiểm thử ví dụ về điều kiện bất nhất:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
String a = "cat";
String b = "dog";

assert !a.equals(b);
assert byLength.compare(a, b) == 0;
```

Đoạn trên cần import `java.util.Comparator`, chạy trong phạm vi phương thức và khi bật assertions (`-ea`). Nó cố ý chứng minh comparator theo độ dài **không nhất quán** với `String.equals`. Để bộ kiểm thử luôn kiểm tra dù assertions bị tắt, dùng một `if` và ném `AssertionError` như ví dụ trước.

## 8. Lỗi phổ biến và cách khắc phục

| Sai sót | Hiện tượng | Cách xử lý |
| --- | --- | --- |
| `Comparator.comparingInt(String::length)` dùng làm thứ tự của `TreeSet<String>` cần lưu mọi chuỗi khác nội dung | Hai chuỗi cùng độ dài bị gộp | Thêm tie-breaker `thenComparing(Comparator.naturalOrder())` hoặc so cả nội dung |
| Comparator trả 0 cho khóa mà `equals` coi là khác | `TreeMap.put` thay giá trị ngoài ý muốn | Dùng các trường định danh làm tiêu chí phân biệt cuối cùng |
| Comparator phân biệt các khóa `equals` bằng nhau | `TreeSet` hoặc `TreeMap` giữ hai mục bằng nhau | Loại trường không tham gia danh tính khỏi tiêu chí phân biệt của cây |
| Cho rằng `TreeSet.contains` luôn gọi `equals` | `contains` có thể trả kết quả khó hiểu | Hiểu nó dựa vào `compare==0` trong thứ tự cây |
| Thêm tie-breaker bằng identity hash | Không bảo đảm uniqueness; phá equality theo giá trị | Dùng thành phần danh tính bền vững và tương thích `equals` |
| Thay đổi khóa sau khi thêm vào `TreeSet`/`TreeMap` | Vị trí cây không còn khớp thứ tự mới | Dùng khóa bất biến; xóa và thêm lại nếu cần |
| Comparator không giữ bắc cầu hoặc tính nhất quán | Sort/lookup có thể sai, một số sort có thể báo lỗi hợp đồng | Kiểm thử cặp và bộ ba, dùng `Comparator.comparing` / `thenComparing` |
| Coi `TreeSet` và `HashSet` là hoàn toàn thay thế được với mọi comparator | Kích thước/tra cứu khác nhau giữa hai kiểu tập | Bảo đảm `compare==0 ⇔ equals` khi cần cùng ngữ nghĩa Set |
| Cố ý gộp khóa không phân biệt hoa thường mà không ghi rõ chính sách | Dữ liệu mất phân biệt chữ hoa và thường ở cây nhưng vẫn phân biệt trong hash | Chuẩn hóa khóa hoặc thiết kế kiểu khóa nhất quán |

## 9. Bài tập tự kiểm tra

**Tình huống 1.** `TreeSet<String>` dùng comparator so độ dài, thêm `"red"` rồi `"sun"`. `size()` và `contains("sun")` có thể là gì?

`size()` bằng 1; `contains("sun")` là `true` vì độ dài đều 3. Tuy nhiên `"red".equals("sun")` là `false`. Nếu muốn cả hai chuỗi, cần thêm tiêu chí phân biệt nội dung trong comparator.

**Tình huống 2.** Hai `Ticket` có cùng `id` nhưng priority 3 và 8. `equals` chỉ so id, comparator so priority rồi id. `TreeSet` có thể lưu mấy phần tử?

Hai phần tử, dù `equals` coi chúng là một. Comparator phân biệt vì priority khác nhau. Nếu khóa logic là id, một tập theo danh tính nên so id làm tiêu chí tương đương.

**Tình huống 3.** Một comparator nhất quán về dấu và bắc cầu nhưng trả 0 cho hai khóa khác nhau theo `equals`. Có phải comparator bị lỗi mọi lúc?

Không. Nó có thể phù hợp khi **chỉ sắp xếp `List`** hoặc ứng dụng chủ ý gom khóa theo chính sách riêng. Nhưng khi dùng làm thứ tự của `TreeSet`/`TreeMap` mà kỳ vọng hợp đồng `Set`/`Map` dựa trên `equals`, nó là không phù hợp.

**Tình huống 4.** Khi thêm khóa mới được comparator xem là bằng khóa đã có trong `TreeMap`, đối tượng khóa ban đầu có chắc được thay bằng đối tượng khóa mới không?

Không. Trong ví dụ ở mục 3, giá trị được thay nhưng entry vẫn giữ `Word[text=cat]` làm khóa. Cần phân biệt **cập nhật giá trị** với **thay đối tượng khóa được lưu**.

**Nguyên tắc áp dụng:** Với tập hoặc bản đồ có thứ tự, hãy xác định ý nghĩa “một phần tử/khóa duy nhất” **trước khi** viết comparator. Khi cần tương thích đúng hợp đồng `Set`/`Map`, bảo đảm `compare(a,b)==0` đúng **khi và chỉ khi** `a.equals(b)`. Nếu chỉ cần sắp xếp để hiển thị, có thể dùng tiêu chí khác trên `List` mà không làm thay đổi danh tính logic của dữ liệu.