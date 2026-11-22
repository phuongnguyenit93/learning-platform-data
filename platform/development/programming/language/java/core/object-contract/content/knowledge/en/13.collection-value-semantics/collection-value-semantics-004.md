# Hash code của List, Set và Map theo hợp đồng tương ứng

## 1. Mục tiêu: hiểu công thức được API quy định

Trong Java Collections Framework, `List`, `Set` và `Map` định nghĩa **quy tắc cụ thể cho `equals(Object)` và `hashCode()`** để các cách cài đặt khác nhau vẫn tương thích khi biểu diễn cùng một giá trị logic.

Điểm mấu chốt: **không có một công thức `hashCode()` chung cho mọi collection**. Ba loại này có ý nghĩa bình đẳng khác nhau:

- **`List`:** dãy phần tử có vị trí, nên thứ tự là một phần của giá trị.
- **`Set`:** tập hợp phần tử không trùng lặp; vị trí/thứ tự duyệt không phải một phần của bình đẳng theo hợp đồng `Set`.
- **`Map`:** tập hợp các ánh xạ từ khóa đến giá trị; thứ tự duyệt/chèn không phải một phần của bình đẳng theo hợp đồng `Map`.

Vì vậy, `List` dùng công thức lũy tiến nhân **31**; `Set` cộng mã băm các phần tử; còn `Map` cộng mã băm các *entry*, mà mỗi entry kết hợp mã băm khóa và giá trị bằng XOR. Đây là các **công thức được Javadoc Java 17 quy định**, không phải chi tiết bucket ngẫu nhiên của riêng `ArrayList`, `HashSet` hoặc `HashMap`.

> Phân biệt kiểu: `List` và `Set` đều mở rộng `Collection`; `Map` **không** mở rộng `Collection`. Chúng thuộc cùng Java Collections Framework nhưng có các hợp đồng riêng.

## 2. Nền tảng: hợp đồng `equals()` và `hashCode()`

Trước khi xét công thức, cần nhớ hợp đồng của `Object`:

1. Nếu `a.equals(b)` trả `true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
2. Nếu hai đối tượng **không** bằng nhau, chúng **vẫn có thể** trùng mã băm (collision); mã băm không phải ID duy nhất.
3. Trong một lần thực thi Java, nếu không có thông tin dùng bởi `equals` thay đổi thì kết quả `hashCode` trên cùng đối tượng phải ổn định.
4. Không có yêu cầu mã băm cố định giữa các lần chạy JVM khác nhau.

Mỗi kiểu `List`/`Set`/`Map` quy định công thức băm để bảo đảm rằng **hai instance bằng nhau về mặt logic, dù thuộc các lớp triển khai khác nhau, có cùng mã băm**.

Ví dụ, một `ArrayList<String>` và một `LinkedList<String>` chứa cùng dãy phần tử có thể bằng nhau; một `HashSet<String>` và `LinkedHashSet<String>` chứa cùng tập phần tử cũng bằng nhau; tương tự cho `HashMap` và `LinkedHashMap` chứa cùng các cặp khóa–giá trị.

Các phần tử, khóa và giá trị tự chúng vẫn phải triển khai `equals/hashCode` đúng hợp đồng. Collection không thể “sửa hộ” một phần tử có cặp phương thức sai.

## 3. `List.hashCode()`: phép tích lũy theo thứ tự

### 3.1. Quy tắc chính thức

Javadoc của `List.hashCode()` quy định thuật toán tương đương:

```java
int hashCode = 1;
for (E element : list) {
    hashCode = 31 * hashCode
            + (element == null ? 0 : element.hashCode());
}
```

Đây là **đoạn mã giả Java theo hợp đồng API**, với biến `list` đại diện cho một danh sách. Nó không phải chương trình độc lập vì `E` và `list` chưa được khai báo.

Giải thích:

- Bắt đầu từ `1`, vì vậy **danh sách rỗng có mã băm bằng `1`**.
- Mỗi phần tử, theo **đúng thứ tự duyệt của danh sách**, đóng góp vào giá trị hiện tại.
- Phần tử `null` đóng góp `0`; công thức vẫn nhân mã băm tích lũy với `31`.
- Các phép nhân/cộng được thực hiện trên `int` của Java; nếu vượt miền 32 bit, giá trị số nguyên tràn theo quy tắc của `int`. Không chuyển thành phép toán số thực, chuỗi hay hash ngẫu nhiên.

Vì phép nhân `31` diễn ra sau từng bước, **thứ tự thường ảnh hưởng mã băm**. Tuy nhiên, hai danh sách khác thứ tự *có thể tình cờ trùng mã băm*; sự khác biệt vị trí làm chúng không bằng nhau theo `List.equals`, chứ không bảo đảm mã băm luôn khác nhau.

### 3.2. Tính thử bằng tay

Với `"A".hashCode() == 65`, `"B".hashCode() == 66`:

| Danh sách | Cách tính | Mã băm |
| --- | --- | ---: |
| `[]` | Giá trị khởi tạo | `1` |
| `["A"]` | `31 × 1 + 65` | `96` |
| `["A", "B"]` | `31 × 96 + 66` | `3042` |
| `["B", "A"]` | `31 × (31 + 66) + 65` | `3072` |
| `["A", null]` | `31 × (31 + 65) + 0` | `2976` |

Thứ tự này khớp với `List.equals`: hai list bằng nhau khi đối tượng còn lại cũng là `List`, có cùng kích thước và từng cặp phần tử tại **cùng vị trí** bằng nhau (xử lý `null` đúng cách).

Hai `List` có cùng phần tử nhưng thứ tự khác nhau không được mặc định xem là bằng nhau. Danh sách cũng có thể chứa phần tử lặp, ví dụ `["A", "A"]`, và mỗi **vị trí** vẫn được tính vào công thức.

### 3.3. Không phụ thuộc vào lớp lưu trữ

Một `ArrayList<>(List.of("A", "B"))` và một `LinkedList<>(List.of("A", "B"))` bằng nhau và đều có `hashCode() == 3042`. Bất kể một lớp dùng mảng, một lớp dùng danh sách liên kết, **hợp đồng `List` quyết định mã băm của chúng**.

Nếu tự triển khai `List`, phải tuân thủ hợp đồng này; chỉ override `equals` mà tính một giá trị băm tùy ý theo vị trí bộ nhớ sẽ phá tính tương thích với các cách triển khai khác.

## 4. `Set.hashCode()`: tổng mã băm các phần tử

### 4.1. Quy tắc chính thức

Theo Javadoc của `Set`, mã băm của tập hợp là **tổng mã băm của các phần tử**, với `null` được coi là `0`:

```java
int hashCode = 0;
for (E element : set) {
    hashCode += (element == null ? 0 : element.hashCode());
}
```

Đây là **đoạn mã giả theo hợp đồng**, không phải tệp Java độc lập.

- **Tập hợp rỗng có mã băm `0`.**
- Thứ tự cộng không thay đổi kết quả số nguyên; mã băm của một tập hợp **không phụ thuộc thứ tự chèn hoặc duyệt**.
- Mỗi phần tử có mặt trong set được cộng một lần; các giá trị bằng nhau không được lưu thành hai phần tử khác biệt theo hợp đồng `Set`.
- Mã băm có thể trùng giữa các tập hợp khác nhau, kể cả khi không có phần tử nào chung.

Ví dụ, `Set.of("A", "B")` có giá trị `65 + 66 = 131`. Một `HashSet` thêm A rồi B và một `LinkedHashSet` thêm B rồi A đều biểu diễn cùng tập và có mã băm `131`. Tập chứa `"A"` và `null`, với triển khai cho phép `null` như `HashSet`, có mã băm `65 + 0 = 65`.

### 4.2. Vì sao không áp dụng công thức `List` cho `Set`?

Một `Set` không có *vị trí phần tử* trong định nghĩa bình đẳng. Nếu mã băm phụ thuộc thứ tự duyệt, hai set bằng nhau nhưng có thứ tự lặp khác nhau có thể nhận mã băm khác nhau, vi phạm `equals => hashCode`.

Định nghĩa `Set.equals` so sánh hai set có cùng kích thước và các phần tử tương đương nhau, **không so vị trí**. Vì vậy công thức tổng là phép kết hợp giao hoán phù hợp với ngữ nghĩa set.

Cần phân biệt việc `LinkedHashSet` duy trì thứ tự lặp với việc thứ tự ấy **không tham gia** `Set.equals/hashCode`. Một lớp có thứ tự duyệt xác định vẫn phải tuân thủ cùng hợp đồng của `Set`.

### 4.3. Collision không vi phạm hợp đồng

Giả sử hai phần tử khác nhau có mã băm `10` và `20`, trong khi một phần tử thứ ba có mã băm `30`. Khi ấy một set chứa hai phần tử đầu và set chứa phần tử thứ ba **có thể cùng mã băm `30`** nhưng không bằng nhau.

Không được kết luận hai set bằng nhau chỉ từ mã băm. Khi cần so sánh chính xác, dùng `set1.equals(set2)`.

## 5. `Map.hashCode()`: tổng mã băm các ánh xạ

### 5.1. Quy tắc chính thức của `Map`

Theo hợp đồng `Map.hashCode()`:

> Mã băm của một map bằng tổng mã băm của các entry trong `entrySet()`.

Viết dưới dạng công thức:

```text
hashCode(map) = Σ hashCode(entry) với mỗi entry ∈ map.entrySet()
```

Đây là công thức của giao diện `Map`, không đòi hỏi map phải được cài bằng bảng băm. Những triển khai khác nhau có cùng các ánh xạ logic phải sinh cùng mã băm.

### 5.2. Mã băm của một `Map.Entry`

`Map.Entry.hashCode()` quy định:

```java
int entryHash = (key == null ? 0 : key.hashCode())
              ^ (value == null ? 0 : value.hashCode());
```

Đây là **đoạn mã minh họa công thức**, trong đó `key` và `value` là các biến chưa khai báo. Ký hiệu `^` trong Java là **bitwise XOR** trên hai số nguyên, **không phải phép lũy thừa**.

Sau đó `Map.hashCode()` cộng các mã băm entry:

```java
int mapHash = 0;
for (Map.Entry<K, V> entry : map.entrySet()) {
    K key = entry.getKey();
    V value = entry.getValue();
    mapHash += (key == null ? 0 : key.hashCode())
            ^ (value == null ? 0 : value.hashCode());
}
```

**Lưu ý về ưu tiên toán tử:** trong biểu thức Java cuối trên, phép cộng `+=` có ưu tiên gán thấp; để thể hiện rõ mỗi entry được XOR trước rồi cộng vào tổng, nên dùng dấu ngoặc như phiên bản sau:

```java
mapHash += ((key == null ? 0 : key.hashCode())
         ^  (value == null ? 0 : value.hashCode()));
```

Nếu sao chép vào mã chạy thực tế, luôn dùng dấu ngoặc này để không nhầm biểu thức và thuận tiện cho người đọc.

### 5.3. Ví dụ tính tay

Với map chứa `"A" -> 1` và `"B" -> 2`:

| Ánh xạ | Mã băm khóa | Mã băm giá trị | Mã băm entry (XOR) |
| --- | ---: | ---: | ---: |
| `"A" -> 1` | `65` | `1` | `65 ^ 1 = 64` |
| `"B" -> 2` | `66` | `2` | `66 ^ 2 = 64` |

Tổng của hai entry là `64 + 64 = 128`. Do phép cộng giao hoán, map thêm B trước A và map thêm A trước B vẫn có mã băm `128` nếu chúng biểu diễn cùng các ánh xạ.

Các trường hợp đặc biệt:

- **Map rỗng:** không có entry nào để cộng, do đó `hashCode() == 0`.
- **Khóa `null` hoặc giá trị `null`:** thành phần mã băm ấy đóng góp `0` nếu triển khai cho phép. Chẳng hạn `HashMap` có `"A" -> null` và `null -> "B"` thì tổng băm là `(65 ^ 0) + (0 ^ 66) = 131`.
- **Đổi giá trị ứng với cùng khóa:** ánh xạ logic đã thay đổi, nên kết quả mã băm có thể thay đổi. Tuy nhiên không phải mỗi lần thay đổi mapping đều bắt buộc tạo mã băm khác; collision vẫn có thể xảy ra.

`Map.equals` so sánh **các ánh xạ**: hai map bằng nhau nếu chứa cùng tập cặp khóa–giá trị theo ngữ nghĩa bình đẳng tương ứng, không xét thứ tự chèn. Vì vậy mã băm dựa trên entry, chứ không chỉ khóa.

## 6. Chương trình Java 17: đối chiếu ba hợp đồng

Ví dụ hoàn chỉnh dùng hai cách triển khai khác nhau cho từng loại. Các phép kiểm tra dựa vào công thức giao diện và dùng dữ liệu `String`/`Integer` có mã băm xác định; không suy luận từ bucket hoặc thứ tự không được bảo đảm của `HashMap`/`HashSet`.

Tạo tệp **`CollectionHashContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionHashContractDemo {
    public static void main(String[] args) {
        List<String> arrayList = new ArrayList<>(List.of("A", "B"));
        List<String> linkedList = new LinkedList<>(List.of("A", "B"));
        List<String> reversedList = List.of("B", "A");
        System.out.println("list equals: " + arrayList.equals(linkedList));
        System.out.println("list hashes: " + arrayList.hashCode()
                + ", " + linkedList.hashCode());
        System.out.println("reversed list hash: " + reversedList.hashCode());
        System.out.println("list with null hash: "
                + Arrays.asList("A", null).hashCode());

        Set<String> hashSet = new HashSet<>(List.of("A", "B"));
        Set<String> linkedSet = new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("set equals: " + hashSet.equals(linkedSet));
        System.out.println("set hashes: " + hashSet.hashCode()
                + ", " + linkedSet.hashCode());
        Set<String> nullSet = new HashSet<>();
        nullSet.add("A");
        nullSet.add(null);
        System.out.println("set with null hash: " + nullSet.hashCode());

        Map<String, Integer> hashMap = new HashMap<>();
        hashMap.put("A", 1);
        hashMap.put("B", 2);
        Map<String, Integer> linkedMap = new LinkedHashMap<>();
        linkedMap.put("B", 2);
        linkedMap.put("A", 1);
        System.out.println("map equals: " + hashMap.equals(linkedMap));
        System.out.println("map hashes: " + hashMap.hashCode()
                + ", " + linkedMap.hashCode());
        System.out.println("map entry A hash: "
                + ("A".hashCode() ^ Integer.hashCode(1)));
        System.out.println("map entry B hash: "
                + ("B".hashCode() ^ Integer.hashCode(2)));
        Map<String, String> nullMap = new HashMap<>();
        nullMap.put("A", null);
        nullMap.put(null, "B");
        System.out.println("map with null hash: " + nullMap.hashCode());

        System.out.println("empty hashes: " + List.of().hashCode()
                + ", " + Set.of().hashCode()
                + ", " + Map.of().hashCode());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 CollectionHashContractDemo.java
java CollectionHashContractDemo
```

**Output đã kiểm chứng:**

```text
list equals: true
list hashes: 3042, 3042
reversed list hash: 3072
list with null hash: 2976
set equals: true
set hashes: 131, 131
set with null hash: 65
map equals: true
map hashes: 128, 128
map entry A hash: 64
map entry B hash: 64
map with null hash: 131
empty hashes: 1, 0, 0
```

Phân tích:

1. **`List`:** `ArrayList` và `LinkedList` chứa cùng `["A","B"]` bằng nhau; cùng mã băm `3042`. Đổi thứ tự cho ví dụ cụ thể tạo mã băm `3072`, đúng công thức phụ thuộc vị trí. `Arrays.asList("A", null)` minh họa quy tắc phần tử `null` đóng góp `0`.
2. **`Set`:** `HashSet` và `LinkedHashSet` bằng nhau dù thứ tự thêm khác nhau; cùng tổng băm `65+66=131`. Tập có `null` dùng mã băm phần tử `0`; `HashSet` cho phép `null`.
3. **`Map`:** `HashMap` và `LinkedHashMap` có cùng hai ánh xạ nên bằng nhau, băm bằng `128`. Mỗi entry trong dữ liệu mẫu có XOR bằng `64`, tổng là `128`. Trường hợp `null` sử dụng `HashMap` vì `HashMap` cho phép khóa/giá trị `null`.
4. **Rỗng:** công thức List khởi tạo `1`, còn Set và Map lấy tổng rỗng `0`. Vì vậy ba mã băm của collection rỗng lần lượt là `1`, `0` và `0`.

**Chú ý API factory:** `List.of(...)`, `Set.of(...)` và `Map.of(...)` **không chấp nhận phần tử/khóa/giá trị `null`**. Ví dụ dùng `Arrays.asList`, `HashSet` và `HashMap` cho các trường hợp có `null`; không thay các dòng ấy bằng `List.of(null)` hoặc `Map.of("A", null)` vì sẽ ném `NullPointerException`.

## 7. So sánh nhanh các công thức

| Kiểu | Điều kiện `equals` chính | Công thức `hashCode` | Có xét thứ tự? | Mã băm khi rỗng |
| --- | --- | --- | --- | ---: |
| `List` | Cùng kích thước, từng phần tử ở vị trí tương ứng bằng nhau | Bắt đầu `1`; với từng phần tử: `h = 31*h + elementHash` | Có, theo thứ tự list | `1` |
| `Set` | Cùng tập phần tử logic, không xét vị trí | Tổng `elementHash` của từng phần tử | Không | `0` |
| `Map` | Cùng các ánh xạ khóa → giá trị logic | Tổng `(keyHash ^ valueHash)` của từng entry | Không | `0` |

Trong bảng, `elementHash`, `keyHash` hoặc `valueHash` bằng `0` khi thành phần tương ứng là `null` (và kiểu collection cho phép `null`).

Đừng nhầm **thứ tự tham gia băm** với **thứ tự duyệt**: một `LinkedHashSet` có thứ tự duyệt cụ thể nhưng mã băm vẫn theo công thức Set không nhạy thứ tự. Tương tự, một `LinkedHashMap` có thể duyệt theo thứ tự chèn nhưng `Map.hashCode` không dựa trên thứ tự entry.

Ngoài ra, một `List` không cần bằng một `Set` chỉ vì chúng chứa cùng tên các phần tử. Hai giao diện định nghĩa bình đẳng **trong cùng loại cấu trúc logic**; không gộp các công thức để so sánh khác loại.

## 8. Mối liên hệ giữa `Map.hashCode()` và `entrySet()`

Theo hai hợp đồng:

```text
Map.hashCode()
  = tổng hashCode của các Map.Entry thuộc entrySet()
  = entrySet().hashCode()
```

Điều này đúng với một `Map` triển khai hợp lệ, vì `entrySet()` là một `Set<Map.Entry<K,V>>` và `Set.hashCode` chính là tổng mã băm phần tử. Lưu ý sự tương đương **của mã băm** ở đây không có nghĩa một `Map` bằng một `Set` theo `equals`.

Phân biệt ba view trên map:

- `keySet()` là một `Set<K>`: băm dựa trên **các khóa**, không chứa mã băm giá trị.
- `values()` là một `Collection<V>`: giao diện `Collection` không quy định một công thức `hashCode` chung như `List` hoặc `Set`; đừng giả sử nó bằng tổng mã băm các giá trị.
- `entrySet()` là một `Set<Map.Entry<K,V>>`: băm dựa trên **các ánh xạ khóa–giá trị**, nên tổng chính là mã băm map.

Chọn đúng view khi cần xử lý khóa, giá trị hoặc toàn bộ ánh xạ; không suy ra băm của map từ `keySet().hashCode()`.

## 9. Các lỗi phổ biến khi triển khai hoặc sử dụng

### 9.1. Dùng cùng công thức băm cho mọi kiểu

Dùng tổng cho `List` sẽ bỏ qua vai trò vị trí và không đáp ứng thuật toán mà giao diện List đã quy định. Dùng nhân `31` cho `Set` theo thứ tự duyệt sẽ khiến hai set bằng nhau có nguy cơ sinh mã băm khác nhau. Với `Map`, chỉ băm khóa sẽ bỏ qua giá trị và không tuân theo công thức `Map.hashCode`.

Không chỉ kiểm tra quy tắc tổng quát “bằng nhau ⇒ cùng băm”; khi triển khai một giao diện cụ thể, hãy tuân thủ **công thức mà chính giao diện đó yêu cầu**.

### 9.2. Tưởng mã băm giống nhau nghĩa là collection bằng nhau

Collision xảy ra ở cả ba loại. Ví dụ `Map.Entry("A", 1)` và `Map.Entry("B", 2)` trong bài có cùng mã băm `64` nhưng không phải cùng ánh xạ. Đừng dùng `hashCode` thay `equals` để quyết định tính bằng nhau.

Thậm chí tổng hash `Set` hoặc `Map` bằng nhau còn dễ xuất hiện trong các cấu hình phần tử khác nhau. Mã băm là dấu hiệu phục vụ tra cứu, **không phải bằng chứng tương đương nội dung**.

### 9.3. Phụ thuộc thứ tự của `HashSet` hoặc `HashMap`

Không đưa thứ tự iterator của `HashSet`/`HashMap` vào phép tính băm theo cách riêng. Hợp đồng Set/Map là độc lập thứ tự. Nếu nghiệp vụ cần thứ tự, dùng đúng collection có cam kết tương ứng; đừng viết `equals/hashCode` dựa trên thứ tự bucket của triển khai hiện tại.

### 9.4. Sửa phần tử hoặc key mutable khi collection làm khóa

Giả sử danh sách `List<String>` được dùng như khóa của một `HashMap`. Nếu nội dung danh sách đổi, `List.hashCode` có thể đổi. Bảng băm bên ngoài không tự di chuyển entry đã lưu theo mã băm mới; lookup có thể thất bại.

Tương tự:

- Trong `HashSet<Person>`, sửa thuộc tính của `Person` dùng trong `equals/hashCode` có thể khiến `contains` không tìm thấy phần tử.
- Với `Map` được dùng làm khóa của map khác, sửa ánh xạ bên trong có thể khiến mã băm của khóa kiểu Map thay đổi.
- Trong `Map<Key, Value>`, sửa **key** khi đang lưu có rủi ro phá lookup của chính map đó; còn sửa value mutable có thể thay đổi mã băm của đối tượng Map **nếu giá trị ấy có hashCode thay đổi**, ngay cả khi map vẫn tra cứu được theo key cũ.

Ưu tiên dữ liệu bất biến khi dùng collection hoặc phần tử làm khóa băm; nếu bắt buộc thay đổi cấu trúc, cân nhắc tạo khóa mới.

### 9.5. Nhầm mảng Java với list giá trị

`int[]`, `String[]` là mảng Java, **không phải `List`**. Mảng không tự dùng công thức `List.hashCode`; so sánh và băm mảng theo nội dung phải dùng `Arrays.equals`/`Arrays.hashCode` (hoặc `deepEquals`/`deepHashCode` phù hợp cho mảng lồng nhau).

Ví dụ, `List.of(new int[]{1,2})` có phần tử là *một mảng*, và mã băm của phần tử ấy dựa trên `int[].hashCode()`, không mặc định dựa trên giá trị `[1,2]`. Nếu muốn bình đẳng theo nội dung, hãy mô hình dữ liệu phù hợp và định nghĩa `equals/hashCode` nhất quán.

### 9.6. Quên xử lý `null` và số nguyên tràn

Hợp đồng nêu `null` đóng góp mã băm `0`. Tuy nhiên việc **collection có cho phép `null` hay không** phụ thuộc lớp/factory cụ thể. `HashSet` và `HashMap` chấp nhận `null`, còn `Set.of` và `Map.of` thì không.

Khi mã băm lớn, phép cộng và nhân của `int` có thể tràn. Đó là hành vi có định nghĩa của phép toán số nguyên Java và là một phần ngữ nghĩa công thức này; **không đổi công thức sang `long` rồi ép kiểu theo một quy trình khác** nếu đang cài đặt hợp đồng giao diện.

### 9.7. Tối ưu hash mà bỏ qua contract

Một `hashCode` “phân bố đẹp” nhưng khác công thức giao diện vẫn sai khi triển khai `List`/`Set`/`Map`. Mục tiêu đầu tiên là đúng API; tối ưu bucket và hiệu năng nằm ở tầng cấu trúc dữ liệu hoặc lựa chọn kiểu phần tử.

## 10. Cách kiểm tra khi review code

Với lớp tự triển khai `List`, `Set` hay `Map`, có thể dùng các phép kiểm tra sau:

1. So sánh instance với một cách triển khai chuẩn tương đương: `ArrayList` ↔ `LinkedList`, `HashSet` ↔ `LinkedHashSet`, `HashMap` ↔ `LinkedHashMap`. Nếu `equals` là `true` thì mã băm phải giống nhau.
2. Tính tay theo công thức giao diện: List bắt đầu từ `1` và nhân `31` theo vị trí; Set cộng mỗi phần tử; Map cộng mỗi entry XOR key/value.
3. Thử trường hợp **rỗng** và **`null`** bằng các lớp cho phép `null`.
4. Thay đổi thứ tự **nhưng giữ cùng nội dung logic**: Set/Map phải giữ mã băm, List có thể đổi (đừng yêu cầu luôn đổi vì collision).
5. Kiểm tra dữ liệu phần tử/khóa/giá trị có tuân thủ `equals/hashCode` và có bị sửa trong khi collection làm khóa băm hay không.
6. Kiểm tra `hashCode` ổn định khi thông tin dùng cho `equals` không thay đổi; không dùng nguồn thời gian hoặc trạng thái bất định.

Khi cần mã nguồn chuẩn để tham khảo, xem tài liệu Oracle Java 17:

- [`List.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()) — công thức nhân 31 theo thứ tự.
- [`Set.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()) — tổng mã băm phần tử.
- [`Map.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#hashCode()) — tổng mã băm các entry.
- [`Map.Entry.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html#hashCode()) — XOR mã băm khóa và giá trị.

## 11. Ghi nhớ

- **`List`:** `h = 1`, sau đó theo từng vị trí `h = 31*h + elementHash`; list rỗng có băm `1`.
- **`Set`:** tổng `elementHash`, không xét thứ tự; set rỗng có băm `0`.
- **`Map`:** tổng `entryHash`, với `entryHash = keyHash ^ valueHash`, không xét thứ tự; map rỗng có băm `0`.
- Thành phần `null` đóng góp mã băm `0`, nhưng không phải collection nào cũng cho phép `null`.
- Hợp đồng bảo đảm **bằng nhau ⇒ cùng băm**, không bảo đảm **cùng băm ⇒ bằng nhau**.
- Khi cài đặt giao diện List/Set/Map, phải theo **công thức chính thức của giao diện**, đồng thời giữ phần tử và khóa ổn định khi chúng tham gia tra cứu bằng bảng băm.
