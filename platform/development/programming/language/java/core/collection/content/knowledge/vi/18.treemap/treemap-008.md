# Chính sách null, tính khả biến của khóa và tính nhất quán phép so sánh

## 1. Ba điều quyết định TreeMap có biểu diễn đúng khóa hay không

TreeMap cần một quan hệ thứ tự để đặt khóa vào cây và tìm lại khóa bằng những lần so sánh.

Vì vậy, chỉ tạo được một TreeMap và gọi put không có nghĩa thiết kế khóa đã hoàn chỉnh. Cần trả lời ba câu hỏi:

1. Khóa null và giá trị null có được phép không?
2. Những thông tin dùng để nhận diện, sắp xếp khóa có giữ ổn định khi khóa đang nằm trong map không?
3. Quan hệ “so sánh bằng 0” có trùng với quan hệ equals của khóa không?

Ba vấn đề có liên hệ, nhưng không được gộp thành một quy tắc mơ hồ như “khóa phải tốt”.

Một Comparator có thể sắp xếp có quy luật nhưng gộp các khóa khác equals. Một lớp khóa có equals/hashCode đúng vẫn có thể bị dùng sai nếu trường sắp xếp bị sửa sau put. Một map cho phép value null không có nghĩa nó cũng cho phép key null.

Bài này tách từng điều kiện, đưa ví dụ chạy được và chỉ rõ đâu là hợp đồng công khai, đâu là kết quả quan sát khi cố ý sử dụng khóa sai cách.

## 2. Khóa, giá trị và thứ tự có vai trò khác nhau

| Thành phần | Vai trò trong TreeMap |
| --- | --- |
| Khóa | Xác định vị trí ánh xạ thông qua quan hệ thứ tự |
| Giá trị | Dữ liệu gắn với khóa; không quyết định đường tìm mặc định |
| `compareTo`/Comparator | Quyết định đi trái, đi phải hoặc xem đã có khóa tương đương |
| `equals` | Quy tắc bằng của đối tượng và nền tảng của hợp đồng Map chung |
| Trạng thái dùng để sắp xếp | Phải tiếp tục phù hợp với vị trí khóa đã được tổ chức trong cây |

TreeMap không dùng hash của khóa để chọn bucket như HashMap. Điều đó không cho phép bỏ qua hợp đồng equals/hashCode của một kiểu khóa dùng chung trong Java; chỉ là đường tìm của TreeMap dựa vào so sánh.

Một khóa có thể được dùng ở các cấu trúc khác, và các thao tác như equals/hashCode của bản thân map cũng có hợp đồng riêng. Thiết kế kiểu dữ liệu không nên đúng cho một lời gọi rồi sai khi chuyển sang ngữ cảnh khác.

## 3. Chính sách null: phân biệt khóa với giá trị

### 3.1. Natural order không nhận khóa null

`new TreeMap<>()` dùng thứ tự tự nhiên của khóa. Các khóa phải có khả năng so sánh phù hợp với nhau; null không phải một khóa hợp lệ trong cấu hình natural order.

`put`(null, value) bị từ chối bằng NullPointerException. Không coi null là “nhỏ nhất mặc định” chỉ vì null có thể xuất hiện trong một số loại Map khác.

Tài liệu [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) nêu điều kiện khóa và các ngoại lệ liên quan tới natural order hoặc Comparator không nhận null.

### 3.2. Comparator riêng có thể cho phép khóa null

Nếu bài toán chủ động cần khóa null, có thể chọn một quan hệ thứ tự nhận null:

```java
Comparator<String> order =
        Comparator.nullsFirst(Comparator.naturalOrder());
Map<String, Integer> map = new TreeMap<>(order);
```

Đây là đoạn khai báo minh họa trong ngữ cảnh có các import phù hợp.

`nullsFirst` xem null đứng trước các khóa khác; nullsLast xem null đứng sau. Các khóa không null được so bằng Comparator bên trong.

Vẫn chỉ có một vị trí khóa null, vì so null với null được xem là bằng 0. `put` lại khóa null cập nhật ánh xạ của vị trí ấy, không tạo vô hạn entry null.

### 3.3. Value null được phép độc lập với chính sách key

Một TreeMap dùng natural order vẫn có thể chứa "beta" → null. Value không cần được so để tìm vị trí khóa "beta".

Do đó, bảng chính sách có thể là:

| Cấu hình | Key null | Value null |
| --- | --- | --- |
| TreeMap dùng natural order | Không cho phép | Cho phép |
| Comparator riêng không xử lý null | Phụ thuộc Comparator, thường bị từ chối khi so | Cho phép |
| Comparator nhận null hợp lệ | Có thể cho phép | Cho phép |

Không suy chính sách key từ chính sách value hoặc ngược lại.

### 3.4. `get` trả null có hai khả năng

`get`("beta") trả null có thể vì:

- Không có khóa "beta".
- Có khóa "beta", nhưng giá trị của nó là null.

Dùng containsKey khi cần phân biệt sự tồn tại. `getOrDefault` chỉ dùng giá trị dự phòng khi khóa không có; nó không thay một ánh xạ đang có value null bằng giá trị dự phòng.

Tương tự, put/remove trả null không luôn đủ để suy ra trước thao tác có ánh xạ hay không.

Nếu kiểm tra tồn tại rồi thực hiện một bước khác trên dữ liệu dùng chung, cần xét tính nguyên tử của cả chuỗi; TreeMap không tự đồng bộ.

### 3.5. Null của đối tượng khóa và null của một trường là hai tầng

Một Comparator so Person theo name có thể cần chính sách cho name null. Điều đó khác với việc cả đối tượng Person là null.

Bọc Comparator của name bằng nullsLast chỉ xử lý giá trị name null khi đã có một đối tượng để lấy trường. Muốn cho phép cả đối tượng khóa null, phải xử lý ở tầng ngoài thích hợp.

Cần xác định đúng nơi null xuất hiện, không bọc tùy ý rồi mong mọi trường hợp đều được giải quyết.

### 3.6. Đừng nhầm hai loại tham số Comparator null

Truyền Comparator null cho constructor TreeMap nghĩa là dùng natural order.

Nhưng truyền null làm Comparator bên trong nullsFirst/nullsLast có ý nghĩa khác: theo hợp đồng các hàm ấy, mọi giá trị không null được xem bằng nhau.

Vì vậy Comparator.nullsFirst(null) không tự có nghĩa “null trước, những giá trị khác theo thứ tự tự nhiên”. Nếu dùng nó cho khóa "a" và "b", hai khóa không null có thể cùng vị trí so sánh.

Hãy truyền rõ Comparator.naturalOrder() hoặc một Comparator đúng cho các giá trị không null. Đối chiếu [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

## 4. Ví dụ Java 17: natural order, nullsFirst và nullsLast

Lưu thành **TreeMapNullPolicy.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapNullPolicy {
    public static void main(String[] args) {
        NavigableMap<String, String> natural = new TreeMap<>();
        try {
            natural.put(null, "not accepted");
        } catch (NullPointerException expected) {
            System.out.println("natural null key: NullPointerException");
        }

        natural.put("beta", null);
        System.out.println("get beta: " + natural.get("beta"));
        System.out.println("contains beta: " + natural.containsKey("beta"));
        System.out.println("get missing: " + natural.get("missing"));
        System.out.println("contains missing: " + natural.containsKey("missing"));
        System.out.println("default beta: " + natural.getOrDefault("beta", "fallback"));
        System.out.println("default missing: " + natural.getOrDefault("missing", "fallback"));

        NavigableMap<String, String> first = new TreeMap<>(
                Comparator.nullsFirst(Comparator.naturalOrder()));
        first.put("b", "B");
        first.put(null, "NULL");
        first.put("a", "A");
        first.put(null, "UPDATED");
        System.out.println("nullsFirst keys: " + new ArrayList<>(first.keySet()));
        System.out.println("null-key value: " + first.get(null));
        System.out.println("nullsFirst size: " + first.size());

        NavigableMap<String, String> last = new TreeMap<>(
                Comparator.nullsLast(Comparator.naturalOrder()));
        last.putAll(first);
        System.out.println("nullsLast keys: " + new ArrayList<>(last.keySet()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapNullPolicy.java
java TreeMapNullPolicy
```

Stdout:

```text
natural null key: NullPointerException
get beta: null
contains beta: true
get missing: null
contains missing: false
default beta: null
default missing: fallback
nullsFirst keys: [null, a, b]
null-key value: UPDATED
nullsFirst size: 3
nullsLast keys: [a, b, null]
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ này chọn mức ngôn ngữ/API và bytecode đích, không thay phiên bản JVM thực thi.

### 4.1. Cùng trả null nhưng trạng thái khác nhau

Beta có ánh xạ với value null, còn missing không có ánh xạ. `containsKey` cho hai kết quả khác nhau.

`getOrDefault` beta vẫn trả null; getOrDefault missing trả fallback.

### 4.2. Thứ tự null là một lựa chọn được công bố

Map first cho dãy null,a,b; map last cho a,b,null. Việc bọc Comparator xác định vị trí null theo quy tắc rõ ràng.

`put` khóa null lần thứ hai thay "NULL" bằng "UPDATED", nên size vẫn là 3.

### 4.3. Một cách chạy thành công không mở rộng hợp đồng

Không dùng một lời gọi tình cờ không lỗi trong một trạng thái đặc biệt để kết luận mọi truy vấn null đều hợp lệ.

Nếu mô hình khóa không cho null, hãy giữ điều kiện đó ở ranh giới dữ liệu. Nếu cho phép, kiểm tra cả thêm, tìm và điều hướng theo Comparator đã chọn.

## 5. Hợp đồng thứ tự và tính nhất quán với equals là hai yêu cầu

### 5.1. Comparator cần tạo thứ tự có quy luật

Một quan hệ dùng cho TreeMap cần tuân hợp đồng Comparator, trong đó có:

- Đảo hai đối số phải đảo dấu kết quả so sánh.
- Quan hệ lớn hơn phải có tính bắc cầu.
- Hai đối tượng so bằng 0 phải có cùng quan hệ dấu khi so với một đối tượng thứ ba.

Kết quả compare không bắt buộc chỉ là -1, 0 hoặc 1; dấu âm, 0 và dấu dương mới là điều quan trọng.

Một phép trừ int trực tiếp để so có thể tràn số. Dùng Integer.compare hoặc Comparator.comparingInt giúp tránh lỗi ấy trong trường hợp số nguyên thông thường.

Một Comparator trả kết quả ngẫu nhiên hoặc đổi chiều tùy lần gọi không tạo cơ sở ổn định cho cây tìm kiếm.

### 5.2. “Nhất quán với equals” có nghĩa chính xác

Với mọi cặp khóa trong miền được hỗ trợ, điều kiện mong muốn là:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

Với miền cho phép null, cần hiểu quan hệ bằng của cả null theo chính sách đã chọn; có thể diễn đạt phép kiểm tra bằng Objects.equals cho miền ấy.

Đây là điều kiện **hai chiều**:

| Trường hợp lệch | Điều có thể xảy ra với TreeMap |
| --- | --- |
| `equals` false nhưng compare bằng 0 | Những khóa khác nhau theo equals bị xem cùng một vị trí |
| `equals` true nhưng compare khác 0 | Những đối tượng cùng khóa theo equals có thể bị tách theo thứ tự |

Chỉ kiểm tra một chiều không đủ.

### 5.3. Một Comparator không nhất quán với equals vẫn có thể có thứ tự hợp lệ

Comparator chỉ nhìn priority của một đối tượng có thể so sánh đúng các mức priority và tuân tính bắc cầu. Nhưng nếu equals của đối tượng xét cả priority lẫn id, hai id khác nhau cùng priority sẽ so bằng 0 dù equals false.

Đây không nhất thiết là một Comparator ngẫu nhiên hay sai tính bắc cầu. Vấn đề là nó định nghĩa lớp tương đương khác với equals của khóa.

TreeMap có hành vi theo quan hệ so sánh ấy. Tài liệu lớp nêu rằng khi thứ tự không nhất quán với equals, cách hành xử của sorted map vẫn được xác định theo thứ tự, nhưng không tuân đầy đủ hợp đồng Map chung.

Không mô tả hiện tượng gộp khóa như cây “làm mất dữ liệu ngẫu nhiên” khi chính Comparator đã nói hai khóa là cùng vị trí.

## 6. Compare bằng 0 ảnh hưởng cả put, get và remove

Khi tìm trong TreeMap, kết quả compare bằng 0 nghĩa đã tới vị trí khóa được xem tương đương.

Hệ quả:

1. `put` một khóa so bằng 0 với khóa đã có có thể thay giá trị của ánh xạ ấy, không tăng size.
2. `get` bằng một đối tượng khác equals nhưng so bằng 0 vẫn có thể tìm cùng ánh xạ.
3. Remove theo một đối tượng so bằng 0 có thể xóa ánh xạ thuộc vị trí tương đương ấy.
4. Điều hướng theo khóa cũng dùng quan hệ so sánh, không tự chuyển sang equals ở bước cuối.

Vì vậy Comparator không chỉ là một tùy chọn trình bày thứ tự khi in. Nó tham gia vào cách TreeMap nhận diện vị trí khóa.

Nếu yêu cầu chỉ là “sắp xếp các mục để hiển thị”, cần cân nhắc việc giữ một Map theo định danh ổn định rồi tạo một dãy đã sắp xếp để hiển thị. Không nhất thiết phải dùng toàn bộ đối tượng hiển thị làm khóa TreeMap.

## 7. Ví dụ Java 17: priority trùng và BigDecimal

Ví dụ đầu dùng record Item(priority, id). `equals` của record xét cả hai thành phần; id được yêu cầu khác null.

Comparator chỉ theo priority sẽ gộp hai Item có cùng priority. Comparator đầy đủ theo priority rồi id phân biệt chúng trong miền dữ liệu này.

Ví dụ tiếp theo dùng BigDecimal để thấy một kiểu thư viện có natural order không nhất quán với equals.

Lưu thành **ComparisonIdentityDemo.java**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class ComparisonIdentityDemo {
    record Item(int priority, String id) {
        Item {
            Objects.requireNonNull(id, "id");
        }
    }

    public static void main(String[] args) {
        Item a = new Item(1, "A");
        Item b = new Item(1, "B");
        Comparator<Item> byPriority = Comparator.comparingInt(Item::priority);
        Map<Item, String> grouped = new TreeMap<>(byPriority);
        grouped.put(a, "first");
        System.out.println("items equal: " + a.equals(b));
        System.out.println("priority comparison: " + byPriority.compare(a, b));
        System.out.println("old value on second put: " + grouped.put(b, "second"));
        System.out.println("priority-only size: " + grouped.size());
        System.out.println("lookup A: " + grouped.get(a));
        System.out.println("lookup B: " + grouped.get(b));

        Comparator<Item> complete = byPriority.thenComparing(Item::id);
        Map<Item, String> separate = new TreeMap<>(complete);
        separate.put(a, "first");
        separate.put(b, "second");
        System.out.println("complete comparison: " + complete.compare(a, b));
        System.out.println("complete size: " + separate.size());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("decimal equals: " + x.equals(y));
        System.out.println("decimal compareTo: " + x.compareTo(y));
        Map<BigDecimal, String> tree = new TreeMap<>();
        Map<BigDecimal, String> hash = new HashMap<>();
        tree.put(x, "one");
        tree.put(y, "two");
        hash.put(x, "one");
        hash.put(y, "two");
        System.out.println("decimal TreeMap size: " + tree.size());
        System.out.println("decimal HashMap size: " + hash.size());

        Comparator<BigDecimal> valueThenScale = Comparator
                .<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
        Map<BigDecimal, String> scaleAware = new TreeMap<>(valueThenScale);
        scaleAware.put(x, "one");
        scaleAware.put(y, "two");
        System.out.println("value-and-scale size: " + scaleAware.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparisonIdentityDemo.java
java ComparisonIdentityDemo
```

Stdout:

```text
items equal: false
priority comparison: 0
old value on second put: first
priority-only size: 1
lookup A: second
lookup B: second
complete comparison: -1
complete size: 2
decimal equals: false
decimal compareTo: 0
decimal TreeMap size: 1
decimal HashMap size: 2
value-and-scale size: 2
```

### 7.1. Priority-only đang giữ một vị trí cho mỗi priority

A và B khác equals, nhưng cùng priority nên compare bằng 0. `put` B trả về giá trị cũ first và thay nó bằng second.

`size` bằng 1 và cả get A lẫn get B cùng tìm thấy second. Điều này theo đúng quan hệ so sánh đã cung cấp.

Nếu yêu cầu là giữ hai đối tượng riêng, Comparator priority-only không diễn đạt yêu cầu đó.

### 7.2. Comparator đầy đủ phù hợp với record này

`thenComparing` id chỉ chạy khi priority bằng nhau. Hai Item chỉ so bằng 0 khi cả priority và id bằng nhau, phù hợp với equals của record trong ví dụ.

Vì vậy hai khóa A và B được giữ riêng, size bằng 2.

Không suy ra thêm một tie-breaker id bất kỳ luôn làm mọi kiểu khóa nhất quán; còn phải biết equals của kiểu khóa ấy xét điều gì.

### 7.3. BigDecimal phân biệt giá trị số với scale

BigDecimal("1.0") và BigDecimal("1.00") có compareTo bằng 0 nhưng equals false: equals còn xét scale.

Vì vậy TreeMap theo natural order có một vị trí so sánh, còn HashMap dùng equals/hashCode giữ hai khóa theo quy tắc của kiểu này.

Đây là đặc tính được mô tả trong [BigDecimal Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), không phải lỗi băm hoặc lỗi cân bằng cây.

Nếu mô hình cần phân biệt theo cả giá trị số và scale, Comparator theo giá trị rồi scale là một lựa chọn có ý nghĩa như phần scaleAware trong chương trình.

Nếu mô hình chỉ quan tâm giá trị số, có thể thiết kế kiểu khóa hoặc bước chuẩn hóa nhất quán với cách nhận diện đó. Chuẩn hóa là một quyết định dữ liệu: không áp tùy tiện nếu scale là thông tin cần giữ.

## 8. Tie-breaker chỉ đúng khi đi cùng mô hình định danh

Giả sử equals của một kiểu thực thể chỉ xét id, nhưng Comparator xét priority rồi id.

Hai đối tượng cùng id nhưng có priority khác nhau vẫn equals true, trong khi Comparator khác 0. Thêm id ở cuối chưa giải quyết chiều lệch này.

Ngược lại, nếu equals xét nhiều thành phần nhưng Comparator bỏ một thành phần có khả năng phân biệt khóa, vẫn có thể gộp các khóa khác equals.

Cần lựa chọn mô hình rõ ràng:

| Yêu cầu | Hướng biểu diễn cần cân nhắc |
| --- | --- |
| Một ánh xạ theo id ổn định | Dùng khóa định danh phù hợp |
| Nhiều mục cùng priority | Giữ danh sách/nhóm theo priority hoặc dùng khóa tổng hợp thật sự phân biệt |
| Sắp xếp để hiển thị | Sắp xếp một dãy mục thay vì thay định danh của map |
| Vừa tra theo id vừa có chỉ mục thứ tự | Thiết kế hai chỉ mục với quy trình cập nhật nhất quán |
| Một khóa tổng hợp là định danh thực | `equals` và Comparator phải cùng thể hiện các thành phần định danh ấy |

Không đưa identityHashCode hoặc một số ngẫu nhiên vào làm tie-breaker chỉ để “không còn compare bằng 0”. Cách đó không tự khớp equals, có thể có va chạm hoặc làm mất ý nghĩa của định danh.

Mục tiêu không phải ép mọi cặp đối tượng có thứ tự khác nhau; mục tiêu là quan hệ thứ tự và quan hệ cùng khóa phù hợp với nhau.

## 9. Vì sao sửa khóa sau khi chèn có thể làm mất đường tìm

### 9.1. Cây lưu vị trí, không liên tục tính lại vị trí

Khi chèn một khóa, TreeMap dùng kết quả so sánh ở thời điểm đó để tổ chức cây. Map giữ tham chiếu tới đối tượng khóa; nó không tự chụp một bản sao bất biến của mọi trường.

Nếu sửa trường mà Comparator đang dùng, kết quả so sánh hiện tại có thể khác kết quả đã dùng để đặt khóa vào cây. Đối tượng vẫn còn được tham chiếu trong một nút, nhưng đường tìm từ gốc theo thứ tự mới có thể đi về phía khác.

Việc duyệt thấy đối tượng không chứng minh get bằng chính tham chiếu ấy sẽ tìm được. Duyệt đi qua các liên kết đang có; tìm theo khóa chọn đường bằng kết quả so sánh hiện tại.

Đây là lý do vấn đề không được giải quyết bằng câu “tôi vẫn dùng đúng object cũ”.

### 9.2. Phân biệt hai loại ràng buộc ổn định

Có hai điều cần giữ:

- Không thay đổi những thông tin ảnh hưởng quan hệ bằng của một khóa trong khi nó đang làm khóa.
- Với TreeMap, quan hệ thứ tự dùng để tổ chức và tìm khóa cũng phải tiếp tục ổn định, phù hợp với cây đã tạo.

Hợp đồng [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) nói hành vi không được xác định khi một đối tượng khóa bị thay đổi theo cách ảnh hưởng phép so sánh equals trong lúc nó nằm trong map.

Riêng cơ chế tìm kiếm có thứ tự còn giải thích vì sao sửa một trường Comparator đọc là nguy hiểm, kể cả khi một thiết kế equals khác không đọc trường ấy. Comparator không thể đổi cách chia trái/phải rồi mong các vị trí cũ tự thích nghi.

Không đồng nhất vấn đề này với va chạm hash: TreeMap không dùng hash để chọn đường tìm. Sửa mỗi hashCode mà không đổi equals hay thứ tự không phải cùng cơ chế hỏng đường tìm vừa mô tả, mặc dù thiết kế kiểu dữ liệu vẫn phải tuân hợp đồng Java của nó.

### 9.3. Final và record chưa luôn có nghĩa bất biến sâu

Một biến tham chiếu final chỉ ngăn gán biến ấy sang đối tượng khác. Nó không tự ngăn thay đổi dữ liệu bên trong đối tượng được tham chiếu.

Record có các thành phần final, nhưng nếu một thành phần là danh sách hay đối tượng khả biến, nội dung bên trong vẫn có thể thay đổi. Nếu Comparator hoặc equals đọc nội dung đó, khóa vẫn có thể thay đổi về mặt quan hệ.

Trong ví dụ an toàn ở phần sau, StableKey chỉ chứa int và String. Không có dữ liệu khả biến bên trong hai thành phần này, nên các thông tin dùng cho equals và Comparator được giữ ổn định.

Không suy từ một ví dụ record an toàn sang mọi record bất kỳ.

### 9.4. Không chỉ đối tượng khóa mới có thể thay đổi thứ tự

Một Comparator có thể đọc trạng thái bên ngoài: bảng ưu tiên có thể sửa, cấu hình đổi chiều hoặc quy tắc phân loại đang thay đổi.

Nếu sửa trạng thái đó làm cùng một cặp khóa cho kết quả so sánh khác trước, cây hiện có cũng không được tự sắp xếp lại. Ngay cả khóa hoàn toàn bất biến cũng không đủ cứu một Comparator đổi quy tắc giữa vòng đời map.

Khi cần một thứ tự mới, hãy tạo một map mới với quy tắc ổn định mới và xây lại chỉ mục từ dữ liệu đáng tin cậy. Không chỉ sửa một cờ trong Comparator của map đang sử dụng.

## 10. Ví dụ Java 17: khóa khả biến và cách thay khóa ổn định

Chương trình có hai thí nghiệm độc lập:

1. Cố ý sửa rank của khóa đang nằm trong một map để quan sát lỗi thiết kế.
2. Dùng một map khác với khóa bất biến, bỏ khóa cũ rồi thêm khóa mới.

Trong thí nghiệm thứ nhất, rank nằm trong cả equals và Comparator. Việc sửa rank khi khóa đang ở trong map rơi vào trường hợp mà hợp đồng Map không xác định hành vi.

**Các dòng bắt đầu bằng observed là kết quả quan sát trên OpenJDK 24.0.2 trong đúng lần chạy này. Chúng không phải kết quả được Java bảo đảm cho mọi cây, mọi thứ tự chèn hoặc mọi phiên bản JVM.**

Lưu thành **MutableTreeKeyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class MutableTreeKeyDemo {
    static final class MutableKey {
        private int rank;
        private final String id;

        MutableKey(int rank, String id) {
            this.rank = rank;
            this.id = Objects.requireNonNull(id, "id");
        }

        int rank() {
            return rank;
        }

        String id() {
            return id;
        }

        void setRank(int rank) {
            this.rank = rank;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && rank == key.rank && id.equals(key.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(rank, id);
        }

        @Override
        public String toString() {
            return id + "@" + rank;
        }
    }

    record StableKey(int rank, String id) {
        StableKey {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public String toString() {
            return id + "@" + rank;
        }
    }

    public static void main(String[] args) {
        Comparator<MutableKey> mutableOrder = Comparator
                .comparingInt(MutableKey::rank)
                .thenComparing(MutableKey::id);
        Map<MutableKey, String> broken = new TreeMap<>(mutableOrder);
        MutableKey a = new MutableKey(1, "A");
        broken.put(a, "value-A");
        broken.put(new MutableKey(2, "B"), "value-B");
        broken.put(new MutableKey(3, "C"), "value-C");
        System.out.println("before mutation: " + new ArrayList<>(broken.keySet()));

        a.setRank(4);
        System.out.println("observed keys after mutation: " + new ArrayList<>(broken.keySet()));
        System.out.println("observed get mutated key: " + broken.get(a));
        System.out.println("observed contains mutated key: " + broken.containsKey(a));

        Comparator<StableKey> stableOrder = Comparator
                .comparingInt(StableKey::rank)
                .thenComparing(StableKey::id);
        Map<StableKey, String> safe = new TreeMap<>(stableOrder);
        StableKey oldKey = new StableKey(1, "A");
        safe.put(oldKey, "value-A");
        safe.put(new StableKey(2, "B"), "value-B");
        safe.put(new StableKey(3, "C"), "value-C");
        String value = safe.remove(oldKey);
        StableKey newKey = new StableKey(4, "A");
        safe.put(newKey, value);
        System.out.println("safe keys: " + new ArrayList<>(safe.keySet()));
        System.out.println("safe lookup: " + safe.get(newKey));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MutableTreeKeyDemo.java
java MutableTreeKeyDemo
```

Stdout trên môi trường nêu trên:

```text
before mutation: [A@1, B@2, C@3]
observed keys after mutation: [A@4, B@2, C@3]
observed get mutated key: null
observed contains mutated key: false
safe keys: [B@2, C@3, A@4]
safe lookup: value-A
```

### 10.1. Dãy quan sát không tự đổi thành thứ tự mới

Trước khi sửa, các rank được duyệt theo 1, 2, 3.

Sau khi sửa A thành rank 4, lần chạy này vẫn duyệt theo các vị trí đã có, tạo dãy A@4, B@2, C@3. Đó không còn là thứ tự tăng dần theo Comparator hiện tại.

Map không nhận thông báo setRank để tự tháo nút rồi chèn lại.

### 10.2. Cùng một tham chiếu vẫn có thể không tìm thấy

Trong lần chạy này, get(a) trả null và containsKey(a) trả false sau khi rank đổi.

Giá trị của A ban đầu là chuỗi khác null, nên kết quả get null ở thí nghiệm này không phải một ánh xạ hợp lệ đang chứa value null như ví dụ phần 4.

Tuy nhiên, không chuyển quan sát này thành quy tắc “sửa khóa thì get chắc chắn trả null”. Một hình dạng cây khác có thể tình cờ vẫn tìm thấy khóa, và việc tình cờ đó không làm cách dùng trở nên đúng.

Cũng không viết kiểm thử yêu cầu mọi phiên bản JVM phải luôn cho đúng ba dòng observed này. Đây là minh họa cho điều kiện sử dụng bị vi phạm, không phải hợp đồng kết quả cần đóng đinh.

### 10.3. Map an toàn thay đối tượng khóa thay vì sửa nó tại chỗ

Phần safe dùng một cây riêng với StableKey. Khóa oldKey được remove khi vẫn còn rank 1, nên đường tìm còn phù hợp với vị trí cũ.

Sau đó chương trình tạo một StableKey mới có rank 4 rồi put lại giá trị. Cây có cơ hội tổ chức ánh xạ mới theo đúng thứ tự hiện tại.

Do ví dụ biết chắc khóa cũ tồn tại và value là chuỗi khác null, biến value nhận lại được "value-A". Ứng dụng cho phép value null cần xử lý thông tin tồn tại riêng, không suy từ remove trả null rằng khóa cũ vắng mặt.

## 11. Quy trình cập nhật và phục hồi chỉ mục

### 11.1. Chọn dữ liệu ổn định làm khóa

Nếu map tra cứu đơn hàng theo mã đơn, mã ổn định thường là khóa tự nhiên hơn toàn bộ đối tượng đơn hàng đang thay đổi.

Giá, trạng thái xử lý hoặc mức ưu tiên có thể nằm ở value. Sửa value không làm đổi vị trí khóa nếu Comparator chỉ đọc khóa và không tham chiếu ngược sang những dữ liệu vừa sửa.

Nếu bài toán thật sự cần chỉ mục theo ưu tiên rồi mã, dùng một ảnh chụp khóa ổn định phù hợp với các thành phần đó. Đối tượng nghiệp vụ có thể thay đổi ở nơi khác; khóa đang nằm trong chỉ mục giữ nguyên giá trị cho tới khi được tháo ra.

Đây là lựa chọn mô hình dữ liệu, không phải yêu cầu mọi đối tượng trong chương trình đều bất biến.

### 11.2. Khi cần đổi khóa, tháo ánh xạ khi khóa cũ còn hợp lệ

Một quy trình có kiểm soát cần xác định:

1. Ánh xạ cũ có tồn tại không, kể cả khi value được phép null?
2. Khóa mới có hợp lệ về null, kiểu và Comparator không?
3. Khóa mới có trùng một vị trí đang có theo Comparator không?
4. Nếu trùng, nghiệp vụ muốn từ chối, hợp nhất hay thay thế giá trị?
5. Khi đã chốt chính sách, tháo khóa cũ khi nó còn hợp lệ và chèn khóa mới ổn định.

Không nên sửa khóa cũ trước rồi mới gọi remove bằng khóa đã sửa. Lúc ấy chính thao tác remove có thể không tìm đúng đường nữa.

Ví dụ phần 10 là trường hợp đơn giản: không có va chạm khóa mới, khóa cũ chắc chắn tồn tại, dữ liệu được dùng trong một luồng. Với dữ liệu dùng chung, các bước kiểm tra và cập nhật còn cần được bảo vệ thành một thao tác nghiệp vụ nhất quán.

Chỉ bọc từng lời gọi riêng lẻ trong một cơ chế đồng bộ không tự làm cả chuỗi kiểm tra–xóa–thêm trở thành nguyên tử.

### 11.3. Đừng dùng remove trả null làm toàn bộ quyết định

Nếu map có thể chứa value null, cả hai tình huống sau đều có thể làm remove trả null:

- Không có ánh xạ cần xóa.
- Đã có và đã xóa một ánh xạ có value null.

Ứng dụng cần giữ thông tin tồn tại bằng cách thích hợp trong cùng phạm vi kiểm soát cập nhật. Khi dùng containsKey rồi remove, phải bảo đảm dữ liệu không bị một thao tác khác thay đổi ở giữa nếu tính đúng phụ thuộc hai bước đó.

Vấn đề này độc lập với việc khóa có bất biến hay không: khóa ổn định giúp tìm đúng vị trí, nhưng không thay ý nghĩa của kết quả null.

### 11.4. Nếu khóa đã bị sửa, ưu tiên nguồn dữ liệu chuẩn

Cách sửa thiết kế đáng tin là lấy dữ liệu chuẩn, tạo khóa ổn định mới, rồi xây một chỉ mục mới dưới Comparator đã chốt.

Cần kiểm tra va chạm theo quan hệ so sánh trong quá trình xây lại. Nếu mô hình cũ đã gộp nhiều khóa khác nhau thành một vị trí, các giá trị từng bị thay thế không tự xuất hiện trở lại chỉ nhờ tạo map mới. Muốn khôi phục chúng phải có nguồn dữ liệu khác còn giữ thông tin.

Không mặc định một constructor sao chép sẽ “sửa cây”. Trong mã nguồn OpenJDK 17, constructor nhận SortedMap và một số đường tối ưu putAll có thể xây từ trình tự được coi là đã sắp xếp. Chúng không phải một giao thức phục hồi dữ liệu bị sử dụng sai. Xem [TreeMap.java của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java).

Nếu cần xây một chỉ mục theo thứ tự mới, hãy chủ động tạo map rỗng với Comparator đúng và đưa từng cặp khóa ổn định–giá trị từ nguồn chuẩn vào đó. Vẫn phải giải quyết khóa trùng theo yêu cầu nghiệp vụ; việc gọi put không tự quyết định thay bạn.

Không hứa một chiến thuật phục hồi tổng quát cho mọi trạng thái có được sau khi đã vi phạm điều kiện sử dụng.

## 12. Ghép ba chính sách thành một thiết kế rõ ràng

### 12.1. Viết chính sách trước khi chọn Comparator

Một ví dụ yêu cầu có thể là:

- Khóa là cặp priority và id.
- Cả đối tượng khóa và id đều không được null.
- Priority và id không đổi khi khóa nằm trong map.
- Hai khóa bằng nhau khi cả hai thành phần bằng nhau.
- Thứ tự là priority tăng dần rồi id tăng dần.
- Giá trị được phép null, nên sự tồn tại được kiểm tra tách với get.
- Khi đổi priority, ứng dụng tạo khóa mới và cập nhật chỉ mục theo quy trình.

Những quyết định này giải thích vì sao Comparator theo priority rồi id phù hợp. Chỉ nhìn một dòng comparingInt mà không biết định danh, null và vòng đời khóa thì chưa đủ đánh giá thiết kế.

Một bài toán khác có thể chọn chính sách khác. Điều cần giữ là các quyết định không mâu thuẫn với nhau.

### 12.2. Kiểu generic rộng không bảo đảm mọi khóa so được với nhau

TreeMap<Object, V> dùng natural order không tự biến mọi Object thành một miền có thứ tự chung. Một số nguyên và một chuỗi không có nghĩa tự nhiên là luôn so sánh được với nhau.

Tương tự, Comparator chấp nhận một kiểu khai báo rộng có thể vẫn đọc một trường chỉ có ở một số đối tượng hoặc từ chối một phần miền giá trị.

Hãy xác định miền khóa thực tế, kiểm tra mọi cặp cần hỗ trợ và xử lý dữ liệu không hợp lệ ở ranh giới nhập. Không dựa vào việc một khóa đầu tiên đã put thành công để suy ra mọi khóa tương lai đều hợp lệ.

### 12.3. Null không phải công cụ chữa khóa bị gộp

Bọc Comparator bằng nullsFirst/nullsLast chỉ bổ sung chính sách cho null. Nó không tự làm phần so sánh các khóa không null nhất quán với equals.

Nếu Comparator bên trong chỉ đọc priority, hai đối tượng khác id cùng priority vẫn có thể so bằng 0 sau khi được bọc.

Ngược lại, bổ sung tie-breaker đúng cho định danh không tự giải quyết null của một trường bên trong. Mỗi tầng phải có chính sách phù hợp.

### 12.4. Đồng bộ không thay thế tính đúng của khóa

Một TreeMap được bảo vệ truy cập bởi khóa đồng bộ vẫn có thể sai thiết kế nếu một luồng sửa trường sắp xếp của khóa khi nó đang nằm trong cây.

Đồng bộ trả lời ai được truy cập và vào thời điểm nào. Nó không tự thay Comparator, giữ ổn định dữ liệu khóa hoặc xây lại các nút sau thay đổi.

Tương tự, chuyển sang một cấu trúc có thứ tự hỗ trợ truy cập đồng thời không tự loại bỏ yêu cầu về quan hệ so sánh và vòng đời khóa.

## 13. Kiểm tra hợp đồng bằng các tình huống có ý nghĩa

### 13.1. Kiểm tra Comparator độc lập trước

Với các khóa thuộc miền hỗ trợ, cần kiểm tra:

| Điều cần kiểm tra | Dấu hiệu mong đợi |
| --- | --- |
| So một khóa với chính nó | Kết quả bằng 0 |
| Đảo a và b | Dấu kết quả đảo chiều |
| a lớn hơn b, b lớn hơn c | a lớn hơn c |
| a và b so bằng 0 | So a với c và b với c phải cho cùng dấu |
| So sánh và equals | Compare bằng 0 khi và chỉ khi Objects.equals đúng trong miền đã chọn |
| Cùng cặp khóa, trạng thái hợp lệ không đổi | Kết quả không đổi qua các lần gọi |

Dùng cả các giá trị biên số nguyên, như MIN_VALUE và MAX_VALUE, để phát hiện cách so bằng phép trừ dễ tràn.

Dùng nhiều đối tượng mới có cùng dữ liệu để tránh kiểm tra duy nhất bằng cùng một tham chiếu. Một Comparator chỉ đúng cho đúng object đã có chưa đủ cho map theo giá trị.

Không lấy vài trường hợp điển hình làm chứng minh toán học cho toàn bộ miền vô hạn. Chúng là kiểm thử phát hiện lỗi; lập luận theo định nghĩa các thành phần vẫn cần thiết.

### 13.2. Kiểm tra null ở đúng tầng

Nếu cấm null, kiểm tra đầu vào bị từ chối theo chính sách đã công bố. Nếu cho phép, kiểm tra null với null, null với khóa thường và các khóa thường với nhau.

Nếu đối tượng khóa có trường có thể null, thêm riêng các trường hợp trường null. Không dùng kết quả xử lý cả đối tượng null để thay cho kiểm tra trường null.

Với nullsFirst/nullsLast, kiểm tra cả hành vi Comparator bên trong. Một lớp bọc hợp lệ không thể sửa phép so sánh sai của phần bên trong.

### 13.3. Kiểm tra thao tác map theo mô hình định danh

Một bộ kiểm tra có ý nghĩa nên bao gồm:

- Hai khóa khác nhau thật sự phải được giữ riêng theo định danh đã chọn.
- Một đối tượng mới bằng khóa cũ phải tìm lại đúng ánh xạ.
- `put` khóa tương đương cập nhật đúng giá trị và không tăng số ánh xạ.
- Remove khóa tương đương tác động đúng ánh xạ.
- Duyệt theo thứ tự đã công bố khi mọi điều kiện sử dụng đều hợp lệ.
- Giá trị null và khóa vắng mặt được phân biệt khi nghiệp vụ cần.
- Thay khóa bằng quy trình an toàn không làm mất dữ liệu hoặc ghi đè ngoài chính sách.

Nếu Comparator cố ý không nhất quán với equals, cần nhận diện rõ quyết định đó và hệ quả với hợp đồng Map. Không viết kiểm thử giả định TreeMap dùng equals để tách các khóa trong trường hợp ấy.

### 13.4. Kiểm tra khóa ổn định và giới hạn của thí nghiệm sai

Xem xét mọi trường Comparator, compareTo, equals và hashCode đọc, cùng mọi dữ liệu khả biến có thể được truy cập gián tiếp từ chúng.

Kiểm thử quy trình đúng bằng khóa mới có cùng dữ liệu, không chỉ kiểm tra get bằng tham chiếu ban đầu. Với chỉ mục có nhiều thành phần, đổi một thành phần phải đi qua quy trình cập nhật đã thiết kế.

Phần cố ý sửa khóa trong bài chỉ giúp nhìn thấy một biểu hiện của việc vi phạm điều kiện. Không dùng các giá trị observed làm đặc tả cho ứng dụng.

## 14. Các lỗi phổ biến và cách nhận diện

| Nhận định hoặc cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| TreeMap cho value null nên key cũng null được | Hai chính sách độc lập | Xem natural order hoặc Comparator cụ thể |
| `get` null nghĩa là không có khóa | Có thể là value null | Kiểm tra sự tồn tại khi cần |
| `nullsFirst`(null) dùng natural order cho phần còn lại | Các khóa không null bị coi là bằng nhau | Truyền Comparator bên trong rõ ràng |
| Comparator chỉ dùng để in có thứ tự | Nó quyết định cả vị trí khóa | Kiểm tra put/get/remove và định danh |
| Hai object khác nhau thì chắc có hai ánh xạ | Compare bằng 0 có thể gộp chúng | Đối chiếu quan hệ so sánh với equals |
| Comparator bắc cầu thì luôn tuân hợp đồng Map | Vẫn có thể lệch equals | Kiểm tra cả hai chiều compare bằng 0 và equals |
| Thêm id ở cuối luôn giải quyết được | `equals` có thể chỉ xét id hoặc xét thành phần khác | Thiết kế từ định danh thật |
| Biến final làm đối tượng khóa bất biến | Dữ liệu bên trong còn có thể sửa | Kiểm tra toàn bộ dữ liệu được quan hệ khóa đọc |
| Sửa khóa xong rồi remove để sửa lại | Remove cũng có thể không tìm đúng đường | Tháo khi khóa cũ còn hợp lệ |
| Duyệt còn thấy khóa thì get chắc thấy | Duyệt và tìm chọn đường khác nhau | Giữ ổn định quan hệ khóa |
| Đổi chiều Comparator thì cây tự đổi chiều | Cây không tự tổ chức lại | Xây chỉ mục mới theo quy tắc mới |
| Chạy một lần vẫn đúng nên cách sửa khóa an toàn | Đã vượt điều kiện hợp đồng | Kiểm tra thiết kế, không dựa vào may mắn |
| Sao chép SortedMap chắc chắn sửa dữ liệu sai | Có đường xây dựng tin thứ tự đầu vào | Dùng nguồn chuẩn và khóa ổn định |
| Đồng bộ truy cập chữa được khóa khả biến | Đồng bộ không tái lập thứ tự đã bị thay đổi | Thiết kế khóa đúng và bảo vệ quy trình cập nhật |

## 15. Bài tập tự kiểm tra

### Bài 1. Value null khác khóa vắng mặt thế nào?

Một TreeMap natural order có "x" → null. `get`("x") và get("y") đều trả null. Cần dùng gì để phân biệt, và getOrDefault("x", "fallback") trả gì?

**Gợi ý trả lời:** containsKey phân biệt sự tồn tại. `getOrDefault` với "x" vẫn trả null vì ánh xạ đã có; với "y" mới dùng fallback.

### Bài 2. Cho null đứng đầu đã đủ chưa?

Một Comparator ngoài dùng nullsFirst, nhưng Comparator bên trong chỉ so priority. Hai khóa không null khác id cùng priority có được giữ riêng không?

**Gợi ý trả lời:** Không chỉ nhờ lớp bọc null. Hai khóa vẫn so bằng 0 theo phần bên trong, nên TreeMap xem cùng một vị trí.

### Bài 3. Comparator có thứ tự hợp lệ nhưng lệch equals

Record Key(int level, String code) có equals mặc định. Comparator chỉ so level. Hai khóa có cùng level nhưng code khác nhau nói lên lỗi gì?

**Gợi ý trả lời:** Có thể vẫn là một thứ tự hợp lệ theo level, nhưng không nhất quán với equals. TreeMap gộp các khóa theo quan hệ so sánh, nên không đáp ứng đầy đủ hợp đồng Map chung theo equals.

### Bài 4. Tie-breaker có đủ không?

Một lớp có equals chỉ xét id. Comparator xét priority rồi id. Hai đối tượng cùng id, khác priority có thỏa điều kiện nhất quán không?

**Gợi ý trả lời:** Không. `equals` true nhưng compare khác 0. Cần thay mô hình khóa hoặc cách tạo chỉ mục theo đúng định danh nghiệp vụ.

### Bài 5. Hai BigDecimal có cùng giá trị số

Nếu dùng new BigDecimal("2.0") và new BigDecimal("2.00") làm khóa TreeMap natural order, tại sao có thể chỉ còn một ánh xạ dù equals false?

**Gợi ý trả lời:** `compareTo` so giá trị số nên bằng 0; equals còn xét scale. TreeMap dùng quan hệ so sánh để xác định cùng vị trí khóa.

### Bài 6. Cùng một tham chiếu có bảo đảm tìm lại?

Sau khi put một đối tượng khóa, sửa trường Comparator đọc rồi get bằng chính đối tượng ấy. Có thể kết luận chắc chắn tìm thấy hoặc chắc chắn không tìm thấy không?

**Gợi ý trả lời:** Không. Vị trí đã xây có thể không còn phù hợp với đường tìm mới; nếu thay đổi còn ảnh hưởng equals thì Map không xác định hành vi trong trường hợp đó. Một kết quả quan sát riêng không tạo bảo đảm.

### Bài 7. Record có luôn an toàn không?

Một record giữ tham chiếu tới danh sách khả biến; Comparator đọc nội dung danh sách. Việc các thành phần record là final đã đủ giữ thứ tự không?

**Gợi ý trả lời:** Chưa đủ. Tham chiếu không đổi nhưng nội dung được đọc có thể đổi. Cần giữ ổn định dữ liệu thực sự quyết định quan hệ khóa.

### Bài 8. Khi nào tháo khóa cũ?

Muốn đổi rank của một ánh xạ đang có, nên sửa rank rồi remove hay remove khi khóa cũ còn hợp lệ rồi tạo khóa mới?

**Gợi ý trả lời:** Tháo ánh xạ khi khóa cũ còn hợp lệ, rồi dùng khóa mới ổn định, đồng thời xử lý tồn tại, value null, va chạm khóa mới và tính nhất quán của cả quy trình khi cần.

### Bài 9. Comparator đọc một cờ đảo chiều

Mọi khóa đều bất biến nhưng Comparator đọc cờ cấu hình có thể đổi từ tăng sang giảm. Đổi cờ có tự đảo lại cây không?

**Gợi ý trả lời:** Không. Thứ tự giữa cùng các khóa đã thay đổi trong khi cấu trúc cũ vẫn còn. Tạo một chỉ mục mới theo quy tắc mới ổn định.

### Bài 10. Có nên đóng đinh kết quả khóa bị sửa?

Một thí nghiệm sửa khóa sau put cho get null trên một JVM. Kiểm thử ứng dụng có nên yêu cầu mọi JVM luôn trả null để phát hiện “lỗi TreeMap” không?

**Gợi ý trả lời:** Không. Thí nghiệm đã dùng khóa ngoài điều kiện hợp đồng. Kiểm thử phải yêu cầu quy trình hợp lệ giữ đúng ánh xạ; biểu hiện sau khi vi phạm không phải đặc tả cần bảo vệ.

## 16. Tài liệu đối chiếu

- [TreeMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): quan hệ thứ tự, hợp đồng Map, chính sách null và các thao tác khóa.
- [Comparator — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): các luật so sánh, tính nhất quán với equals, nullsFirst/nullsLast và thenComparing.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): ý nghĩa khóa bằng nhau, value null và điều kiện sử dụng khóa khả biến.
- [BigDecimal — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): quan hệ giữa compareTo, equals và scale.
- [TreeMap.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): cơ chế tìm theo Comparator và các đường xây dựng từ dữ liệu được coi là có thứ tự. Chi tiết triển khai cần gắn với phiên bản; hợp đồng API mới là cơ sở cho cách dùng hợp lệ.
