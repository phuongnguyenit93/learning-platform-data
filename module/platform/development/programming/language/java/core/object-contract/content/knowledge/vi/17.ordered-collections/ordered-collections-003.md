# Hai đối tượng `equals()` true nhưng `Comparator` phân biệt

Một tình huống dễ gây bất ngờ trong Java: **hai đối tượng được `equals()` coi là bằng nhau, nhưng `Comparator.compare(a, b)` lại trả về số khác `0`**. Khi đưa chúng vào `HashSet`, có thể chỉ còn một phần tử; khi đưa vào `TreeSet` dùng comparator đó, cả hai lại cùng tồn tại.

Đây không phải vì `TreeSet` bỏ qua việc kiểm tra khóa trùng do lỗi. **`TreeSet` xác định phần tử tương đương bằng kết quả so sánh thứ tự**, còn `HashSet` xác định phần tử bằng `equals` và `hashCode`. Nếu hai định nghĩa về sự tương đương không thống nhất, hai cấu trúc có thể cho kết quả khác nhau. Với một `SortedSet` muốn tuân thủ đầy đủ hợp đồng chung của `Set`, thứ tự dùng để xác định trùng phần tử **phải nhất quán với `equals`**.

Bài học này tập trung vào chiều dễ bỏ sót: **`a.equals(b) == true` nhưng `comparator.compare(a, b) != 0`**, lý do gây ra, hệ quả khi dùng tập hợp/bản đồ có thứ tự, và cách thiết kế để tránh lỗi nghiệp vụ.

## 1. Hai quan hệ “bằng nhau” khác nhau

Trong Java có hai câu hỏi riêng:

- `a.equals(b)`: hai đối tượng có được kiểu dữ liệu xem là **cùng giá trị logic** không?
- `comparator.compare(a, b)`: hai đối tượng **đứng trước, tương đương, hay đứng sau** nhau theo một quy tắc sắp xếp cụ thể?

`Comparator<T>.compare(a, b)` trả về số âm nếu `a` đứng trước `b`, `0` nếu chúng tương đương theo **thứ tự**, hoặc số dương nếu `a` đứng sau `b`. Không phải mọi comparator đều phải dùng cùng các trường với `equals`. Điều đó có thể phù hợp khi **chỉ sắp xếp `List`**. Nhưng khi comparator làm quy tắc phân biệt key trong `TreeSet` hoặc `TreeMap`, sự khác biệt có thể thay đổi ý nghĩa của “trùng”.

Một quan hệ thứ tự **nhất quán với `equals`** khi, với hai đối tượng hợp lệ:

~~~text
comparator.compare(a, b) == 0  ⇔  a.equals(b) == true
~~~

Dấu `⇔` nghĩa là **hai chiều đều phải đúng**: `equals` bằng nhau thì `compare` bằng `0`, và `compare` bằng `0` thì `equals` bằng nhau. Bảng phân biệt:

| `a.equals(b)` | `compare(a, b) == 0` | Diễn giải |
| --- | --- | --- |
| `true` | `true` | Hai quan hệ cùng coi đối tượng là tương đương. |
| `false` | `false` | Hai quan hệ cùng phân biệt đối tượng. |
| **`true`** | **`false`** | **Trường hợp trọng tâm:** `equals` gộp, comparator lại tách. |
| `false` | `true` | Chiều ngược lại: comparator gộp hai đối tượng `equals` xem là khác. |

Một comparator **không nhất quán với `equals`** chưa hẳn là comparator sai về thứ tự. Nó vẫn có thể hợp lệ cho việc sắp xếp danh sách. Sự rủi ro xuất hiện khi đem thứ tự đó làm cơ sở xác định **tính duy nhất** trong tập hợp có thứ tự hoặc key trong bản đồ có thứ tự.

## 2. Ví dụ Java 17+: `equals` true, `compare` khác 0

Giả sử `Item` có `id` và `revision`:

- Hai `Item` có **cùng `id`** được hệ thống coi là cùng thực thể logic. Vì thế `equals` và `hashCode` chỉ xét `id`.
- Một màn hình lại muốn sắp xếp theo `id`, rồi theo `revision` để biết phiên bản nào đứng trước. Comparator này xét **cả hai trường**.

Tệp đầy đủ **`ComparatorEqualsMismatchDemo.java`**, biên dịch và chạy trên Java 17+:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorEqualsMismatchDemo {
    static final class Item {
        private final int id;
        private final int revision;

        Item(int id, int revision) {
            this.id = id;
            this.revision = revision;
        }

        int id() {
            return id;
        }

        int revision() {
            return revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Item that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return "Item(" + id + "," + revision + ")";
        }
    }

    public static void main(String[] args) {
        Item first = new Item(7, 1);
        Item second = new Item(7, 2);
        Item query = new Item(7, 3);

        Comparator<Item> byIdThenRevision =
            Comparator.comparingInt(Item::id)
                      .thenComparingInt(Item::revision);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(byIdThenRevision.compare(first, second));
        System.out.println(byIdThenRevision.compare(second, first));

        Set<Item> hashSet = new HashSet<>();
        hashSet.add(first);
        hashSet.add(second);
        System.out.println(hashSet.size());
        System.out.println(hashSet.contains(query));

        Set<Item> treeSet = new TreeSet<>(byIdThenRevision);
        treeSet.add(first);
        treeSet.add(second);
        System.out.println(treeSet.size());
        System.out.println(treeSet);
        System.out.println(treeSet.contains(second));
        System.out.println(treeSet.contains(query));

        Comparator<Item> byIdOnly = Comparator.comparingInt(Item::id);
        Set<Item> consistentTreeSet = new TreeSet<>(byIdOnly);
        consistentTreeSet.add(first);
        consistentTreeSet.add(second);
        System.out.println(consistentTreeSet.size());
        System.out.println(consistentTreeSet.contains(query));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ComparatorEqualsMismatchDemo.java
java ComparatorEqualsMismatchDemo
~~~

Kết quả chính xác:

~~~text
false
true
true
-1
1
1
true
2
[Item(7,1), Item(7,2)]
true
false
1
true
~~~

**Đọc kết quả theo ba phần:**

1. `first == second` là `false`: chúng là hai đối tượng riêng. `first.equals(second)` là `true`: `equals` chỉ xét `id = 7`. Vì `hashCode` cũng dùng `id`, hai đối tượng bằng nhau có cùng hash, đáp ứng hợp đồng `equals`/`hashCode`.
2. `byIdThenRevision.compare(first, second)` là `-1` vì `1 < 2` ở trường `revision`; chiều ngược lại là `1`. **Comparator phân biệt hai đối tượng mà `equals` coi là bằng nhau.**
3. `HashSet` dùng ngữ nghĩa `equals`/`hashCode`, nên sau hai lần `add` chỉ có **1 phần tử**; `contains(query)` trả `true` vì `query.id` cũng là `7`.
4. `TreeSet` sử dụng `byIdThenRevision`: vì `compare(first, second) != 0`, cả hai được giữ. Kích thước thành **2**; tập duyệt theo thứ tự `Item(7,1)`, rồi `Item(7,2)`.
5. `treeSet.contains(second)` là `true`. Nhưng `treeSet.contains(query)` là **`false`** dù `query.equals(first)` và `query.equals(second)` đều là `true`: theo comparator, `Item(7,3)` là một giá trị thứ tự khác.
6. Khi thay comparator bằng **`byIdOnly`**, hai `Item` cùng `id = 7` được so bằng `0`, trùng với cách `equals` định nghĩa sự bằng nhau. `TreeSet` khi đó chỉ có **1 phần tử**, và tìm `query` trả `true`.

Ví dụ có `Item` là `final`, các trường `final` và `hashCode` ổn định; do đó sự khác biệt giữa hai tập ở đây **chỉ đến từ quy tắc tương đương của comparator**, không phải do sửa đổi đối tượng sau khi chèn hay do lỗi hash.

## 3. Vì sao `TreeSet` có thể chứa hai phần tử `equals() == true`?

Giao diện `Set` mô tả tập hợp không có hai phần tử trùng nhau theo `equals`. Tuy nhiên, `SortedSet` và `TreeSet` cần dùng **thứ tự sắp xếp** để tìm đúng vị trí khi thêm, tìm hoặc xóa.

Với `TreeSet`:

1. Nếu được truyền `Comparator`, tập dùng `comparator.compare(x, y)` để sắp xếp và phân biệt phần tử.
2. Nếu không có `Comparator`, tập dùng thứ tự tự nhiên từ `Comparable.compareTo` của phần tử.
3. Khi kết quả so sánh là `0`, tập coi hai đối tượng là **tương đương theo thứ tự**, nên thêm đối tượng sau không tăng kích thước.
4. Khi kết quả so sánh khác `0`, tập có thể lưu hai phần tử ở hai vị trí phân biệt, **kể cả khi `equals` trả `true`**.

Đây là lý do tài liệu của `SortedSet` yêu cầu **thứ tự phải nhất quán với `equals` nếu muốn cấu trúc tuân thủ đúng hợp đồng chung của `Set`**. Hành vi của một sorted set với comparator không nhất quán vẫn có thể được xác định rõ bởi comparator, nhưng các kỳ vọng từ `Set` thông thường sẽ bị vi phạm.

### Minh họa sự khác nhau về “đơn vị duy nhất”

| Cấu trúc | Hai `Item(7,1)` và `Item(7,2)` |
| --- | --- |
| `HashSet<Item>` | Coi trùng vì `equals` theo `id`; giữ một phần tử. |
| `TreeSet<Item>` với comparator `id` rồi `revision` | Coi khác vì kết quả so sánh khác `0`; giữ hai phần tử. |
| `TreeSet<Item>` với comparator chỉ theo `id` | Coi trùng vì kết quả so sánh bằng `0`; giữ một phần tử. |

Đừng giải thích hiện tượng bằng câu “`TreeSet` dùng `hashCode` khác `HashSet`”. `TreeSet` là cấu trúc dựa trên thứ tự, **không dùng `hashCode` để xác định phần tử tương đương**. Một `hashCode` hoàn toàn đúng vẫn không sửa được comparator sai so với ngữ nghĩa tập hợp.

## 4. Điều gì xảy ra với `TreeMap` và các khóa `equals` bằng nhau?

Tình huống tương tự xảy ra ở `TreeMap`: một `Comparator` không nhất quán với `equals` có thể khiến hai key logic bằng nhau trở thành **hai entry**.

Tệp **`TreeMapComparatorDemo.java`** có thể biên dịch độc lập trên Java 17+:

~~~java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapComparatorDemo {
    record Key(int id, int revision) {
        @Override
        public boolean equals(Object obj) {
            return obj instanceof Key that && id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Key first = new Key(7, 1);
        Key second = new Key(7, 2);

        Comparator<Key> byBoth =
            Comparator.comparingInt(Key::id)
                      .thenComparingInt(Key::revision);

        Map<Key, String> hash = new HashMap<>();
        System.out.println(hash.put(first, "old"));
        System.out.println(hash.put(second, "new"));
        System.out.println(hash.size());
        System.out.println(hash.get(first));

        Map<Key, String> tree = new TreeMap<>(byBoth);
        System.out.println(tree.put(first, "old"));
        System.out.println(tree.put(second, "new"));
        System.out.println(tree.size());
        System.out.println(tree.get(first));
        System.out.println(tree.get(second));
        System.out.println(tree.containsKey(new Key(7, 3)));
    }
}
~~~

Chạy:

~~~bash
javac TreeMapComparatorDemo.java
java TreeMapComparatorDemo
~~~

Kết quả chuẩn:

~~~text
null
old
1
new
null
null
2
old
new
false
~~~

Ở `HashMap`, `second` trùng khóa logic với `first`, nên `put(second, "new")` thay giá trị `"old"`, kích thước vẫn là `1`.

Ở `TreeMap` dùng comparator `id` rồi `revision`, hai key khác nhau theo quan hệ thứ tự, nên `put(second, "new")` thêm entry mới, kích thước thành `2`. Truy vấn với `new Key(7,3)` không tìm thấy key có cùng vị trí thứ tự, dù key đó `equals` với cả hai key đã lưu.

Điều này có thể ảnh hưởng đến chức năng cập nhật theo ID, chống trùng, tra cứu và xóa: **quy tắc chọn comparator cho `TreeMap` là một quyết định về danh tính khóa trong cấu trúc đó**, không chỉ là lựa chọn hiển thị.

Trong ví dụ, record `Key` đã **override cả `equals` lẫn `hashCode`** để dùng `id` làm khóa logic; đây là khác biệt có chủ đích so với `equals` tự sinh của record mặc định vốn xét cả `id` và `revision`.

## 5. Khi nào comparator không nhất quán với `equals` vẫn hữu ích?

Không có quy định rằng **mọi** comparator dùng để sắp xếp phải nhất quán với `equals`. Một comparator có thể sắp xếp theo nhiều tiêu chí để trình bày tốt hơn, miễn là nó đáp ứng hợp đồng về **thứ tự** như tính đối xứng về dấu, tính bắc cầu và tính nhất quán của các nhóm `compare == 0`.

Chẳng hạn, nếu muốn hiển thị tất cả revision của những đối tượng có cùng `id`, bạn có thể sắp xếp **một danh sách** bằng comparator xét `id` và `revision`:

~~~java
List<Item> items = new ArrayList<>();
items.add(new Item(7, 2));
items.add(new Item(7, 1));

items.sort(
    Comparator.comparingInt(Item::id)
              .thenComparingInt(Item::revision)
);
System.out.println(items);
~~~

Đoạn trên dùng lớp `Item` đã định nghĩa ở mục 2 và cần các import `java.util.List`, `java.util.ArrayList`, `java.util.Comparator`. Khi đặt trong phương thức `main` cùng lớp `Item`, đầu ra là:

~~~text
[Item(7,1), Item(7,2)]
~~~

Danh sách **không xóa phần tử trùng theo `equals`**, nên việc giữ cả hai revision là hành vi bình thường và comparator nhiều tiêu chí giúp hiển thị đúng ý định. Vấn đề phát sinh khi **cũng chính comparator này** được đưa vào `TreeSet`/ `TreeMap` nhưng chương trình lại trông đợi tập hợp hoặc bản đồ thực thi khái niệm trùng theo `id`.

### “Bằng nhau về đối tượng” và “phân biệt bản trình bày”

Nếu `id` xác định thực thể, còn `revision` là thuộc tính phiên bản, có thể hợp lý khi:

- Dùng `equals` theo `id` cho đối tượng thực thể.
- Dùng `Comparator` theo `id` rồi `revision` để **xếp thứ tự các bản trình bày trong danh sách**.
- Dùng `TreeSet`/ `TreeMap` **theo `id`** nếu cần lưu đúng một phần tử/key cho mỗi thực thể logic.
- Hoặc thiết kế kiểu khóa riêng `(id, revision)` nếu mục tiêu thật sự là giữ **mỗi phiên bản như một khóa khác nhau**.

Như vậy, cần tách việc “muốn nhìn các đối tượng theo thứ tự nào” khỏi việc “muốn lưu bao nhiêu giá trị khác nhau theo quy tắc nào”.

## 6. Cách sửa khi cần một `TreeSet` nhất quán với `equals`

Với `Item.equals` chỉ xét `id`, comparator tương ứng có thể là:

~~~java
Comparator<Item> byLogicalIdentity =
    Comparator.comparingInt(Item::id);

Set<Item> set = new TreeSet<>(byLogicalIdentity);
set.add(new Item(7, 1));
set.add(new Item(7, 2));

System.out.println(set.size()); // 1
~~~

Ở đây `compare(a, b) == 0` khi và chỉ khi hai đối tượng có cùng `id`, trùng với cách `equals` đã định nghĩa. Comparator không còn phân biệt các revision có cùng `id`.

Tùy yêu cầu nghiệp vụ, có ba hướng sửa hợp lý:

1. **Giữ `equals` theo ID, sửa comparator của sorted set/map theo ID.** Thích hợp khi bạn muốn một entry cho mỗi thực thể.
2. **Nếu revision thực sự là thành phần của danh tính**, đưa revision vào **cả `equals`, `hashCode` và comparator**. Khi đó `Item(7,1)` và `Item(7,2)` thực sự là hai giá trị khác nhau, phù hợp việc giữ cả hai.
3. **Nếu chỉ cần thứ tự trình bày**, giữ comparator theo ID + revision cho thao tác sắp xếp `List`. Dùng collection khác cho việc khử trùng theo `equals`, hoặc tách kiểu khóa biểu diễn mỗi revision.

Không nên vá bằng cách thay `hashCode` nhưng giữ `equals` và comparator cũ: `TreeSet` không dựa vào hash để quyết định trùng. Cũng không nên tự thêm `if (a.equals(b)) return 0;` vào đầu một comparator bất kỳ mà chưa chứng minh tính bắc cầu và nhất quán của các nhóm tương đương. Một comparator trộn quy tắc theo cách tùy tiện có thể phá hợp đồng so sánh.

## 7. Hợp đồng `Comparator` vẫn bắt buộc dù không nhất quán với `equals`

Tính nhất quán với `equals` là điều rất nên có cho sorted set/map, nhưng `Comparator` vẫn phải thỏa các quy tắc về quan hệ thứ tự:

- **Đổi chiều đổi dấu:** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
- **Bắc cầu:** nếu `a > b` và `b > c` thì `a > c`.
- **Nhóm tương đương nhất quán:** nếu `compare(a,b) == 0`, thì dấu so sánh của `a` với một đối tượng `z` phải bằng dấu so sánh của `b` với `z`.
- **Tính ổn định:** kết quả nên không thay đổi khi những trường dùng để so sánh không đổi.

`Comparator.comparingInt(Item::id).thenComparingInt(Item::revision)` ở ví dụ là một thứ tự hợp lý, không vi phạm các tính chất trên. Nó chỉ **không nhất quán với `Item.equals`** vì xét thêm `revision`.

Tránh viết `return a.id() - b.id();`: phép trừ số nguyên có thể tràn `int` và đảo dấu kết quả, khiến comparator bị sai. `Integer.compare` hoặc `Comparator.comparingInt` xử lý so sánh số nguyên an toàn hơn.

Với đối tượng đặt trong `TreeSet` hoặc làm key của `TreeMap`, không thay đổi các trường tham gia comparator sau khi thêm vào cấu trúc. Nếu thứ tự bị đổi ngầm mà cây không được xây lại, thao tác `contains`, `get` hoặc `remove` có thể trả kết quả ngoài mong đợi. Các ví dụ trong bài dùng trường `final` để tránh hiện tượng này.

## 8. Nhận diện tình huống lỗi trong mã thực tế

Một số dấu hiệu đáng kiểm tra:

- `HashSet.size()` khác `TreeSet.size()` dù chèn cùng các giá trị. Kiểm tra xem comparator có trả `0` đúng cho từng cặp `equals == true` hay không.
- `TreeSet.contains(x)` là `false` dù bạn tìm được một phần tử `y` trong tập mà `x.equals(y) == true`. Có thể comparator phân biệt `x` và `y`.
- `TreeMap.put(k2, v2)` tạo entry mới dù `k1.equals(k2) == true`. Nếu dùng comparator không nhất quán với `equals`, hai key có thể đứng ở hai vị trí khác nhau trong cây.
- Một comparator `thenComparing(...)` được thêm “để phân biệt khi trùng tiêu chí” nhưng tiêu chí phụ lại **không có trong `equals`**. Đây là điểm cần xem lại khi comparator phục vụ sorted set/map.
- Comparator chỉ so một trường trong khi `equals` so nhiều trường, tạo tình huống ngược lại: `compare == 0` dù `equals == false`, khiến sorted set/map gộp các giá trị khác nhau theo nghiệp vụ.

Không phải cứ thấy `equals == true` và `compare != 0` là phải chỉnh lại mọi comparator. Hãy kiểm tra comparator được dùng **chỉ để sắp xếp** hay còn được dùng để **quyết định tính duy nhất và tra cứu**.

## 9. Bài tập kiểm chứng

Với `Item.equals` chỉ xét `id`, `hashCode` theo `id`, và comparator xét lần lượt `id`, `revision`, hãy tự trả lời trước khi chạy code:

1. `new Item(7,1).equals(new Item(7,2))` cho kết quả gì? Comparator của hai đối tượng trả dấu gì?
2. Thêm hai `Item` trên vào `HashSet` rồi `TreeSet` dùng comparator hai trường. Kích thước từng tập là bao nhiêu? Vì sao?
3. `TreeSet.contains(new Item(7,3))` trả gì nếu tập đang chứa `Item(7,1)` và `Item(7,2)`? Trong khi đó, `HashSet.contains(new Item(7,3))` trả gì?
4. Nếu sửa `TreeSet` để so theo `id` duy nhất, kích thước có thay đổi không? Hành vi nào trở nên nhất quán với `equals`?
5. Nếu nhu cầu thật là lưu từng revision như một phần tử độc lập, có nên thay `equals`/`hashCode` để cùng xét `id` và `revision` hay không? Điều này phụ thuộc quy tắc nghiệp vụ nào?
6. Tại sao việc chỉ chỉnh `hashCode` không giải quyết được trường hợp `TreeSet` giữ hai đối tượng `equals == true`?

**Ghi nhớ:** **`equals(a,b) == true` không tự buộc một comparator tùy biến phải trả `0`**. Nhưng `TreeSet` và `TreeMap` dùng **kết quả `compare == 0`** để xác định phần tử/key tương đương, nên comparator không nhất quán với `equals` có thể tạo ra “trùng theo `equals` nhưng khác trong cây”. Khi cần sorted set/map tuân thủ đúng ngữ nghĩa tập hợp/bản đồ theo giá trị, hãy bảo đảm **`compare(a,b) == 0` khi và chỉ khi `a.equals(b)`**; nếu chỉ cần sắp xếp khác biệt, hãy dùng comparator đó với danh sách.