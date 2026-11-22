# `List.equals()` xét phần tử theo thứ tự

## 1. Hai danh sách bằng nhau khi nào?

Trong Java, `java.util.List.equals(Object)` xác định **bằng nhau theo giá trị của một dãy có thứ tự**. Hai danh sách được xem là bằng nhau khi và chỉ khi:

1. Đối tượng đem so sánh cũng là một `List`.
2. Hai danh sách có **cùng số lượng phần tử**.
3. Với mỗi chỉ số hợp lệ `i`, phần tử ở vị trí `i` của danh sách thứ nhất bằng phần tử ở **đúng vị trí `i`** của danh sách thứ hai. Nếu cả hai phần tử là `null` thì được xem là bằng nhau tại vị trí đó; nếu không, so sánh bằng `equals` của phần tử.

Diễn đạt bằng điều kiện:

```text
left.equals(right)
    = right là List
      AND left.size() == right.size()
      AND mọi i trong [0, size):
          Objects.equals(left.get(i), right.get(i)) == true
```

Đoạn trên là **mô tả khái niệm**, không phải mã thư viện Java hay bản cài đặt tối ưu. API không bắt buộc phải gọi `get(i)` trên từng phần tử theo cách trên; việc duyệt bằng iterator thường phù hợp hơn cho một số implementation, chẳng hạn danh sách liên kết.

Ví dụ:

```text
["Java", "Spring"] ==giá_trị==> ["Java", "Spring"]    đúng
["Java", "Spring"] ==giá_trị==> ["Spring", "Java"]    sai
["Java", "Java"]   ==giá_trị==> ["Java"]             sai
```

**Thứ tự và số lần xuất hiện đều quan trọng.** Chỉ có cùng những phần tử, hoặc cùng tổng số phần tử, là chưa đủ. Đây là đặc điểm thiết yếu phân biệt `List` với `Set`.

Trong phần dưới, `list.equals(other)` luôn là phép so sánh giá trị. Biểu thức `list == other` lại hỏi hai biến có cùng tham chiếu không.

## 2. Quy tắc theo từng chỉ số

Hãy so sánh:

```java
List<String> a = List.of("A", "B", "A");
List<String> b = List.of("A", "B", "A");
List<String> c = List.of("A", "A", "B");
```

Các đoạn trên dùng kiểu `List` và có thể đặt trong một phương thức sau khi `import java.util.List;`; chưa phải một tệp hoàn chỉnh.

| Chỉ số | `a` | `b` | `c` | `a` so với `b` | `a` so với `c` |
| --- | --- | --- | --- | --- | --- |
| 0 | A | A | A | Bằng | Bằng |
| 1 | B | B | A | Bằng | **Khác** |
| 2 | A | A | B | Bằng | Khác |

Vì thế `a.equals(b)` là `true` còn `a.equals(c)` là `false`. Dù `a` và `c` có cùng tập giá trị và cùng số lần xuất hiện từng giá trị, chúng có **thứ tự khác nhau**. `List.equals` không tự sắp xếp lại trước khi so sánh.

Những trường hợp cần ghi nhớ:

- **Danh sách rỗng:** hai `List` rỗng bằng nhau, kể cả khác implementation; một danh sách rỗng không bằng danh sách có một phần tử `null`.
- **Độ dài khác:** kết quả `false` dù phần đầu của danh sách dài trùng hoàn toàn với danh sách ngắn.
- **Phần tử lặp:** `["x","x","y"]` khác `["x","y","x"]`. Một `Set` có thể loại phần tử lặp, `List` thì giữ.
- **Đổi vị trí hai phần tử bằng nhau:** không làm danh sách khác về giá trị, vì phép so sánh tại mỗi vị trí vẫn đúng.
- **Đổi vị trí hai phần tử khác nhau:** thường làm kết quả `equals` thay đổi, trừ khi các vị trí liên quan vẫn chứa những phần tử được coi là bằng nhau theo chính `equals` của chúng.

## 3. Không phụ thuộc implementation cụ thể

`List.equals` là **hợp đồng của interface `List`**. Vì vậy, hai danh sách cùng phần tử và thứ tự phải bằng nhau dù một bên là `ArrayList`, bên kia là `LinkedList`, hay một danh sách không thể sửa được tạo bởi `List.of`.

```java
// Đặt trong main với các import java.util.* tương ứng.
List<String> array = new ArrayList<>(List.of("one", "two"));
List<String> linked = new LinkedList<>(List.of("one", "two"));

System.out.println(array == linked);       // false
System.out.println(array.equals(linked));  // true
System.out.println(linked.equals(array));  // true
```

Hai biến trỏ đến **hai đối tượng khác nhau** và **hai lớp triển khai khác nhau**, nhưng nội dung dãy tương đương. Điều này minh họa tính đối xứng của hợp đồng `equals`.

Không nên cài đặt `equals` của một lớp `List` tùy biến theo kiểu bắt buộc `obj.getClass() == getClass()`, bởi như vậy có thể làm một `List` mới không bằng `ArrayList` cùng phần tử, trái với hợp đồng chung của `List`.

Về bản chất, tính bằng nhau của `List` **không phụ thuộc** khả năng sửa được, dung lượng cấp phát nội bộ, cách lưu phần tử hay lớp triển khai. Những thuộc tính đó có thể ảnh hưởng đến hiệu năng và hành vi thao tác thêm/xóa, nhưng không nên làm thay đổi kết quả so sánh giá trị.

## 4. Giá trị bằng nhau của từng phần tử: `equals`, kiểu và `null`

### Phần tử được so sánh theo hợp đồng riêng

`List.equals` không biết thế nào là hai phần tử "giống nhau" về nghiệp vụ; nó dựa vào `equals` của từng phần tử. Chẳng hạn:

```java
record Book(String isbn) {}

List<Book> first = List.of(new Book("978-1"));
List<Book> second = List.of(new Book("978-1"));

System.out.println(first.equals(second)); // true
```

Đoạn trên minh họa một `record` và hai danh sách; có thể đặt các khai báo đúng vị trí trong một tệp Java 17+. Record `Book` tự có `equals` dựa trên `isbn`, nên hai đối tượng `Book` khác tham chiếu vẫn bằng nhau.

Ngược lại, nếu `Book` là lớp thông thường không override `equals`, hai lần `new Book(...)` sẽ không tự động bằng nhau chỉ vì các trường trùng nội dung. Kết quả `List.equals` vì thế cũng sẽ là `false`.

Một danh sách `List<Integer>` chứa `1` khác giá trị so với một `List<Long>` chứa `1L`: `Integer.equals(Long)` trả `false`. Java không tự chuyển kiểu số để làm bằng nhau ở cấp phần tử.

### Phần tử `null`

Một số implementation cho phép chứa `null`, ví dụ `ArrayList`. Hai vị trí cùng `null` được coi là bằng nhau:

```java
List<String> withNull1 = new ArrayList<>(Arrays.asList("A", null));
List<String> withNull2 = new LinkedList<>(Arrays.asList("A", null));

System.out.println(withNull1.equals(withNull2)); // true
```

`List.equals` có cách so sánh tương đương `Objects.equals(elementA, elementB)`: hai `null` bằng nhau, một `null` và một phần tử khác `null` thì không. **`List.of(...)` không chấp nhận phần tử `null`** và sẽ ném `NullPointerException` khi tạo danh sách; đây là giới hạn của factory, không phải quy tắc rằng `List.equals` cấm `null`.

Nếu chính biến danh sách là `null`, gọi `list.equals(other)` sẽ ném `NullPointerException`; có thể dùng `Objects.equals(listA, listB)` khi một trong hai **tham chiếu danh sách** có thể `null`. Phải phân biệt danh sách `[null]` (một phần tử) với tham chiếu danh sách `null` (không có đối tượng `List`).

## 5. Ví dụ Java 17 độc lập: kiểm tra thứ tự và implementation

Tạo tệp `ListEqualsOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Set;

public class ListEqualsOrderDemo {
    record Ticket(String code) {}

    public static void main(String[] args) {
        List<String> a = new ArrayList<>(List.of("A", "B", "A"));
        List<String> same = new LinkedList<>(List.of("A", "B", "A"));
        List<String> reordered = List.of("A", "A", "B");
        List<String> shorter = List.of("A", "B");

        System.out.println("same reference: " + (a == same));
        System.out.println("same sequence: " + a.equals(same));
        System.out.println("symmetric: " + same.equals(a));
        System.out.println("different order: " + a.equals(reordered));
        System.out.println("different size: " + a.equals(shorter));
        System.out.println("hash agrees: "
                + (a.hashCode() == same.hashCode()));

        List<String> withNull = new ArrayList<>(
                Arrays.asList("A", null));
        List<String> otherNull = new LinkedList<>(
                Arrays.asList("A", null));
        System.out.println("same null position: "
                + withNull.equals(otherNull));
        System.out.println("null vs nonnull: "
                + withNull.equals(List.of("A", "B")));

        List<Ticket> t1 = List.of(new Ticket("X"));
        List<Ticket> t2 = List.of(new Ticket("X"));
        System.out.println("record elements: " + t1.equals(t2));

        List<List<Integer>> nested1 =
                List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nested2 =
                List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nestedReordered =
                List.of(List.of(3), List.of(1, 2));
        System.out.println("nested same: "
                + nested1.equals(nested2));
        System.out.println("nested reordered: "
                + nested1.equals(nestedReordered));

        Set<String> leftSet =
                new HashSet<>(List.of("A", "B"));
        Set<String> rightSet =
                new HashSet<>(List.of("B", "A"));
        System.out.println("set ignores order: "
                + leftSet.equals(rightSet));
    }
}
```

Lệnh chạy:

```bash
javac ListEqualsOrderDemo.java
java ListEqualsOrderDemo
```

Kết quả:

```text
same reference: false
same sequence: true
symmetric: true
different order: false
different size: false
hash agrees: true
same null position: true
null vs nonnull: false
record elements: true
nested same: true
nested reordered: false
set ignores order: true
```

**Giải thích:** `a` là `ArrayList`, `same` là `LinkedList`. Hai đối tượng không cùng tham chiếu nhưng bằng nhau vì ba vị trí khớp. `reordered` giữ cùng số lần xuất hiện các chữ nhưng đổi thứ tự, nên không bằng `a`. `shorter` thiếu phần tử cuối, không bằng `a`. Các phần còn lại minh họa so sánh `null`, đối tượng giá trị dưới dạng record, danh sách lồng nhau và sự khác nhau giữa `List` với `Set`.

Lưu ý `HashSet` ở cuối chỉ dùng để đối chiếu khái niệm: `Set.equals` dựa trên việc chứa cùng các phần tử, **không quan tâm thứ tự duyệt**. Không nên dùng `new HashSet<>(listA).equals(new HashSet<>(listB))` để thay cho `List.equals`, vì việc chuyển sang `Set` có thể làm mất thông tin thứ tự **và số lần xuất hiện**.

## 6. `List.hashCode()` cũng phụ thuộc thứ tự

Hợp đồng của `List` quy định `hashCode()` được tính tuần tự từ phần tử đầu đến cuối. Tư duy thuật toán:

```java
// Thuật toán mô tả theo hợp đồng List; list là một biến List có sẵn.
int hash = 1;
for (Object element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

Đây là đoạn minh họa, không phải một chương trình độc lập. Phép toán `int` có thể tràn theo quy tắc số nguyên Java; đó là một phần của cách tính hash, không phải lỗi.

Hệ quả:

- Hai `List` bằng nhau phải có cùng hash, dù thuộc những implementation khác nhau.
- Thứ tự các phần tử có thể ảnh hưởng hash. Ví dụ, với phần tử `String`, `["A","B"]` thường có hash khác `["B","A"]`.
- Hai danh sách **khác nhau** vẫn có thể có cùng hash do collision; không được dùng `hashCode()` thay cho `equals()` để kết luận hai dãy bằng nhau.
- Phần tử `null` đóng góp `0` ở vị trí tương ứng; nó vẫn chiếm một vị trí trong dãy và ảnh hưởng số lần áp dụng phép nhân `31`.
- Nếu phần tử trong danh sách thay đổi dữ liệu quyết định `equals/hashCode`, hash của chính danh sách có thể thay đổi, dù bạn không thêm/xóa phần tử trong danh sách.

Ví dụ `["A","B"]` có hash:

```text
Bắt đầu h = 1
Sau "A": h = 31 * 1  + 65 = 96
Sau "B": h = 31 * 96 + 66 = 3042

Với ["B","A"]:
Sau "B": h = 31 * 1  + 66 = 97
Sau "A": h = 31 * 97 + 65 = 3072
```

Những phép tính này minh họa việc **đổi thứ tự dẫn tới mã băm khác** trong ví dụ cụ thể. Chúng không chứng minh mọi phép hoán vị đều cho mã băm khác.

## 7. Khác biệt với `Arrays.equals`, `Objects.equals`, `Set.equals`

| Cách so sánh | Ý nghĩa | Điểm cần phân biệt |
| --- | --- | --- |
| `listA.equals(listB)` | So sánh độ dài và từng phần tử **theo thứ tự**, đối số phải là `List`. | Dùng hợp đồng `equals` của từng phần tử. |
| `Objects.equals(listA, listB)` | So sánh hai tham chiếu có thể `null` an toàn. | Khi cả hai là danh sách khác `null`, ủy quyền tới `listA.equals(listB)`. |
| `Arrays.equals(arrayA, arrayB)` | So sánh nội dung hai mảng cùng kiểu tương ứng theo vị trí. | Phải gọi `Arrays.equals`, vì mảng Java tự nó không override `Object.equals`. |
| `Arrays.deepEquals(arrayA, arrayB)` | So sánh sâu mảng tham chiếu, xử lý phần tử là mảng lồng nhau. | Không tự biến so sánh `List` thành tập hợp không thứ tự. |
| `setA.equals(setB)` | Hai `Set` có cùng phần tử theo quan hệ bằng nhau của phần tử. | Không quan tâm thứ tự và không chứa phần tử trùng. |
| `listA == listB` | So sánh hai tham chiếu `List`. | Không so sánh nội dung dãy. |

**Danh sách chứa mảng là bẫy thường gặp.** Nếu `List<int[]>` chứa hai mảng `new int[]{1,2}` khác nhau, `List.equals` sẽ gọi `equals` của phần tử mảng; mảng dùng mặc định `Object.equals` theo **tham chiếu**. Vì vậy hai danh sách có phần tử mảng chứa cùng các số vẫn có thể **không bằng nhau**. Khi muốn so nội dung mảng, phải thiết kế so sánh phần tử bằng `Arrays.equals` hoặc chuyển sang những kiểu giá trị phù hợp.

**Danh sách lồng danh sách** có hành vi khác: vì mỗi phần tử bên trong cũng là `List`, so sánh từng phần tử sẽ gọi `List.equals` ở cấp tiếp theo, theo thứ tự của từng danh sách con. Đây là lý do `nested1.equals(nested2)` trong ví dụ trả `true`.

## 8. Khi danh sách hoặc phần tử thay đổi

Vì `equals` và `hashCode` của `List` phụ thuộc vào **nội dung có thứ tự tại thời điểm gọi**, các thao tác sau có thể làm kết quả thay đổi:

- `add`, `remove`, `clear`: đổi số lượng và/hoặc các vị trí.
- `set(index, value)`: giữ kích thước nhưng đổi phần tử tại một vị trí.
- `Collections.sort`, `Collections.reverse`, hoặc đổi thứ tự thủ công: giữ tập phần tử nhưng thay đổi thứ tự.
- Sửa **trạng thái bên trong một phần tử mutable** có tham gia `equals/hashCode`: dãy giữ nguyên tham chiếu ở từng vị trí nhưng ý nghĩa bằng nhau có thể đổi.
- Sửa nội dung một **danh sách con** trong `List<List<T>>`: danh sách ngoài có thể đổi kết quả `equals/hashCode` dù chưa thêm hoặc xóa phần tử ngoài.

Khi dùng một `List` mutable làm khóa `HashMap` hoặc phần tử của `HashSet`, các thay đổi kể trên có thể làm giá trị hash đổi trong khi cấu trúc băm **không tự lập chỉ mục lại entry**. Hệ quả là `containsKey`, `get`, `contains`, `remove` có thể không tìm được entry đã lưu. Vì vậy, khóa phải giữ ổn định về `equals/hashCode` trong suốt thời gian tồn tại ở cấu trúc băm.

Ví dụ minh họa dùng tệp độc lập `ListKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ListKeyDemo {
    public static void main(String[] args) {
        List<String> key = new ArrayList<>(List.of("A"));
        Map<List<String>, String> map = new HashMap<>();
        map.put(key, "saved");

        int before = key.hashCode();
        System.out.println("before: "
                + map.get(List.of("A")));

        key.add("B");
        int after = key.hashCode();
        System.out.println("hash changed: " + (before != after));
        System.out.println("content after: "
                + key.equals(List.of("A", "B")));
        System.out.println("map size: " + map.size());

        List<String> safeKey = List.copyOf(key);
        Map<List<String>, String> safeMap = new HashMap<>();
        safeMap.put(safeKey, "new");
        key.add("C");

        System.out.println("safe key unchanged: "
                + safeKey.equals(List.of("A", "B")));
        System.out.println("safe lookup: "
                + safeMap.get(List.of("A", "B")));
    }
}
```

```bash
javac ListKeyDemo.java
java ListKeyDemo
```

Stdout:

```text
before: saved
hash changed: true
content after: true
map size: 1
safe key unchanged: true
safe lookup: new
```

Không in `map.get(key)` sau khi sửa vì kết quả phụ thuộc cách bảng băm tra cứu; ví dụ tập trung vào điều chắc chắn: **danh sách được sửa, hash đổi, nhưng entry cũ vẫn tồn tại**. `List.copyOf(key)` tạo một danh sách không sửa được và không bị thay đổi bởi thao tác thêm phần tử vào `key` sau đó. Với `String` bất biến, giá trị của `safeKey` cũng ổn định.

Cần phân biệt **không sửa được danh sách** với **bất biến sâu**. Nếu `List.copyOf` chứa những đối tượng mutable, sửa trạng thái của phần tử có thể vẫn làm thay đổi kết quả `equals/hashCode` của danh sách được sao chép. Nếu cần một khóa băm ổn định, phải bảo đảm cả các phần tử và những dữ liệu con mà phép bằng nhau phụ thuộc cũng ổn định.

## 9. Độ phức tạp, hợp đồng và một số lỗi thực tế

Đối với hai danh sách có cùng kích thước `n`, việc so sánh có thể phải xét đến `n` cặp phần tử; độ phức tạp tổng quát của một lần duyệt tuyến tính là **O(n)** cộng thêm chi phí `equals` của từng phần tử. Nó có thể dừng sớm ngay khi phát hiện khác nhau ở một vị trí. Nếu kích thước khác, có thể loại ngay. Bản thân `List.equals` không yêu cầu sắp xếp hay phân tích tập hợp, nên không nên tự chuyển dữ liệu thành `Set` để so sánh khi thứ tự quan trọng.

Những nhầm lẫn dễ gặp:

1. **Chỉ kiểm tra `containsAll`:** `a.containsAll(b)` và `b.containsAll(a)` không chứng minh hai danh sách bằng nhau; thiếu kiểm tra thứ tự và số lần lặp.
2. **Chuyển sang `HashSet` rồi so:** mất thông tin thứ tự và phần tử lặp, dẫn đến `true` cho những danh sách không bằng nhau.
3. **So bằng `==`:** chỉ so tham chiếu, bỏ qua hai danh sách khác instance nhưng cùng nội dung.
4. **So bằng `toString()`:** biểu diễn chuỗi dùng cho hiển thị, không phải hợp đồng bình đẳng. Hai kiểu dữ liệu khác nhau có thể có chuỗi tương tự; một số phần tử có `toString` không phù hợp để định danh.
5. **So riêng hash:** cùng `hashCode` không chứng minh `equals` là `true`.
6. **Tự viết `equals` cho custom `List` nhưng quên quy tắc đối xứng/kiểu:** một `ArrayList` và custom list cùng dãy phải tuân thủ hợp đồng của `List`; lỗi triển khai custom có thể làm hai hướng cho kết quả khác nhau.
7. **Dùng `List.of` với `null`:** factory này cấm `null`, dù nhiều implementation khác cho phép.
8. **Nghĩ `List.copyOf` khiến mọi đối tượng con bất biến:** bản sao không sửa được ở cấp danh sách nhưng phần tử mutable vẫn có thể bị sửa.
9. **So sánh hai danh sách đang bị sửa đồng thời:** nếu collection không được đồng bộ thích hợp, có thể có kết quả không ổn định hoặc ngoại lệ; phải tạo snapshot ổn định hay dùng cơ chế phối hợp phù hợp trước khi so sánh.

Nếu một đối tượng phần tử cài đặt `equals` sai hợp đồng (chẳng hạn không đối xứng hoặc bắc cầu), so sánh ở cấp danh sách cũng có thể biểu lộ sự bất nhất. `List.equals` **dựa vào** `equals` của phần tử và không tự sửa các lỗi ở cấp phần tử.

## 10. Checklist và tự kiểm tra

Trước khi quyết định hai danh sách có bằng nhau hay không, hãy hỏi:

- Có cùng số phần tử không? `[]` khác `[null]`.
- Mỗi chỉ số có một cặp phần tử bằng nhau theo `equals` không?
- Việc lặp phần tử và vị trí xuất hiện có ảnh hưởng đến nghiệp vụ không?
- Các phần tử có định nghĩa `equals` phù hợp không, đặc biệt với class tự tạo hoặc mảng?
- Cần so sánh `List` có thể `null` không? Nếu có, dùng `Objects.equals` cho **tham chiếu danh sách**.
- Danh sách hoặc phần tử có thể sửa không? Nếu dùng làm khóa băm, tính ổn định phải được đảm bảo.
- Yêu cầu thực sự là "cùng dãy có thứ tự" hay "cùng tập phần tử"? Chọn `List.equals` hoặc `Set.equals` theo **ngữ nghĩa nghiệp vụ**.

**Câu hỏi tự luyện:**

1. `List.of(1, 2, 1).equals(List.of(1, 1, 2))` trả gì? Vì sao?
2. `new ArrayList<>(List.of("a")).equals(new LinkedList<>(List.of("a")))` trả gì?
3. Hai `List` cùng kích thước, cùng hash có nhất thiết `equals == true` không?
4. `[null, "x"]` và `["x", null]` có bằng nhau không nếu implementation đều cho phép `null`?
5. Vì sao `List<int[]>` thường không so nội dung của từng mảng như mong đợi?
6. Đổi vị trí hai phần tử có thể làm `List.hashCode` đổi không? Có bắt buộc mọi lần đổi vị trí đều làm hash khác không?
7. Vì sao `List.copyOf` chứa các phần tử mutable vẫn có thể không phù hợp làm khóa băm?
8. Khi ứng dụng không quan tâm thứ tự nhưng cần loại phần tử lặp, nên biểu diễn bằng `List` hay `Set`?

**Ghi nhớ:** `List.equals()` so sánh **độ dài và từng cặp phần tử ở cùng chỉ số**, không phụ thuộc implementation. **Thứ tự và số lần xuất hiện đều có ý nghĩa**. `List.hashCode()` cũng được tính theo thứ tự, vì vậy hãy giữ dữ liệu liên quan đến bình đẳng ổn định khi dùng danh sách trong cấu trúc băm.