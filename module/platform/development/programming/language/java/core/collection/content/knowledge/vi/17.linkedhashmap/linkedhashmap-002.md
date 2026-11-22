# Thứ tự chèn và hành vi thay giá trị của khóa đã có

## 1. LinkedHashMap giữ một trật tự bên cạnh các ánh xạ

Một map lưu ánh xạ từ khóa đến giá trị. `LinkedHashMap` còn duy trì một thứ tự duyệt xác định. Với chế độ mặc định, đó là **thứ tự chèn (insertion order)**.

Giả sử lần lượt thêm các khóa `B`, `A`, `C`:

```text
put("B", 2)
put("A", 1)
put("C", 3)

Thứ tự duyệt khóa: B → A → C
```

Kết quả không tự thành `A → B → C`, vì thứ tự chèn không phải thứ tự sắp xếp theo khóa.

Nếu sau đó gọi `put("A", 100)`, map đổi giá trị của `A` nhưng vẫn duyệt theo:

```text
B → A → C
```

Khóa `A` không tự chuyển xuống cuối chỉ vì được ghi lại. Đây là quy tắc chính của bài: **trong LinkedHashMap theo thứ tự chèn, thay giá trị một khóa đang có giữ nguyên vị trí của khóa đó**.

### Vì sao hành vi này hữu ích?

Một báo cáo có thể muốn giữ thứ tự các trường được thêm ban đầu, nhưng vẫn cho sửa số liệu của từng trường. Một bộ cấu hình có thể giữ thứ tự hiển thị đã thiết lập, trong khi các giá trị được cập nhật nhiều lần.

`LinkedHashMap` theo thứ tự chèn đáp ứng dạng yêu cầu “giữ vị trí đã có, cập nhật nội dung”. Nếu ứng dụng muốn thứ tự theo lần sửa gần nhất, đó là một yêu cầu khác cần thiết kế rõ.

Các ví dụ dưới dùng `LinkedHashMap` thông thường, không ghi đè chính sách tự loại bỏ phần tử. Trừ phần đối chiếu chế độ ở cuối, mọi map đều dùng thứ tự chèn mặc định và API tương thích Java 17.

## 2. Thứ tự chèn chính xác là thứ tự của lần tạo ánh xạ đang tồn tại

Cần phân biệt ba sự kiện:

| Sự kiện | Có tạo ánh xạ mới không? | Tác động lên thứ tự chèn |
|---|---|---|
| `put` với khóa chưa có | Có | Thêm khóa ở cuối |
| `put` với khóa đang có | Không; thay giá trị | Giữ vị trí |
| `remove` rồi `put` lại khóa đó | Có một lần chèn mới sau khi đã xóa | Khóa xuất hiện ở cuối khi chèn lại |

Cụm “thứ tự chèn” không có nghĩa map nhớ mãi vị trí của lần xuất hiện đầu tiên trong toàn bộ lịch sử chương trình. Khi ánh xạ bị xóa, vị trí ấy không được dành chỗ để phục hồi tự động về sau.

Ví dụ:

```text
Ban đầu:           B → A → C
put("A", 100):     B → A → C
remove("A"):       B → C
put("A", 200):     B → C → A
```

`put` vào khóa đang tồn tại và xóa–chèn lại là hai chuỗi thay đổi khác nhau, dù cuối cùng đều có thể để lại cùng giá trị cho khóa đó.

### Vị trí không phải chỉ số để truy cập như List

Một `LinkedHashMap` có thứ tự duyệt, nhưng không vì thế trở thành một danh sách hỗ trợ `get(0)` để lấy phần tử đầu.

`map.get(key)` vẫn là tra theo khóa. Nếu khóa là số nguyên `0`, `get(0)` tìm ánh xạ của khóa `0`, không phải “phần tử ở vị trí số 0”.

Khi cần một danh sách khóa có chỉ số, có thể tạo một `List` riêng từ `keySet`; đó là một cấu trúc khác với map.

## 3. Vì sao thay giá trị không làm đổi vị trí?

Về mô hình, `LinkedHashMap` kết hợp khả năng tìm khóa của map băm với một chuỗi liên kết qua các ánh xạ để xác định thứ tự duyệt.

Có thể hình dung:

```text
Thứ tự:   [B] ⇄ [A] ⇄ [C]
Giá trị:   2     1     3
```

Sau khi thay giá trị của `A`:

```text
Thứ tự:   [B] ⇄ [A] ⇄ [C]
Giá trị:   2    100    3
```

Ánh xạ logic của `A` đã có, nên việc thay nội dung không phải lần tạo một vị trí mới ở cuối.

Khi thêm `D` mới:

```text
Thứ tự:   [B] ⇄ [A] ⇄ [C] ⇄ [D]
```

Khi xóa `A`, nó không còn trong chuỗi thứ tự. Chèn lại sau đó tạo vị trí ở cuối, không phải phục hồi khoảng trống cũ.

Đây là mô hình giải thích, không yêu cầu ứng dụng tự quản lý các liên kết nội bộ. Việc mở rộng bảng băm hoặc phân bố bucket không tự biến thứ tự chèn thành thứ tự theo mã băm hay thứ tự khóa.

### Có thứ tự không thay thế hợp đồng khóa

`LinkedHashMap` vẫn cần một định nghĩa khóa đúng. Hai đối tượng khóa khác nhau nhưng bằng nhau theo `equals` và nhất quán về `hashCode` đại diện cùng một khóa logic.

Vì vậy `put(new String("A"), 100)` không tự tạo một vị trí mới nếu đang có khóa chuỗi `"A"`. Đối tượng mới được cấp phát khác với việc có một khóa logic mới.

Cũng không dùng cách sửa thông tin định danh của đối tượng khóa để “đổi vị trí” hoặc “đổi tên” khóa. Khóa phải giữ hợp đồng ổn định trong thời gian làm khóa; thứ tự có thể dự đoán không chữa được một khóa làm sai cơ chế tìm kiếm.

## 4. Chương trình đầy đủ: ghi lại, đọc, xóa và chèn lại

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapInsertionDemo {
    public static void main(String[] args) {
        Map<String, Integer> numbers = new LinkedHashMap<>();
        numbers.put("B", 2);
        numbers.put("A", 1);
        numbers.put("C", 3);
        System.out.println("initialKeys=" + numbers.keySet());
        System.out.println("initialValues=" + numbers.values());

        Integer old = numbers.put(new String("A"), 100);
        System.out.println("replacementOld=" + old);
        System.out.println("afterReplaceKeys=" + numbers.keySet());
        System.out.println("afterReplaceMap=" + numbers);
        System.out.println("sizeAfterReplace=" + numbers.size());

        System.out.println("sameValueOld=" + numbers.put("B", 2));
        System.out.println("afterSameValueKeys=" + numbers.keySet());
        System.out.println("readB=" + numbers.get("B"));
        System.out.println("afterReadKeys=" + numbers.keySet());

        numbers.put("D", 4);
        System.out.println("afterNewKey=" + numbers.keySet());
        System.out.println("removedA=" + numbers.remove("A"));
        System.out.println("afterRemove=" + numbers.keySet());
        numbers.put("A", 200);
        System.out.println("afterReinsert=" + numbers.keySet());
        System.out.println("finalMap=" + numbers);

        Map<String, Integer> nullable = new LinkedHashMap<>();
        nullable.put(null, null);
        nullable.put("X", 1);
        System.out.println("nullKeyOld=" + nullable.put(null, 2));
        System.out.println("nullableKeys=" + nullable.keySet());
        System.out.println("nullableSize=" + nullable.size());
        System.out.println("nullKeyNow=" + nullable.get(null));
    }
}
```

Lưu thành `LinkedHashMapInsertionDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapInsertionDemo.java
java LinkedHashMapInsertionDemo
```

Đầu ra chính xác:

```text
initialKeys=[B, A, C]
initialValues=[2, 1, 3]
replacementOld=1
afterReplaceKeys=[B, A, C]
afterReplaceMap={B=2, A=100, C=3}
sizeAfterReplace=3
sameValueOld=2
afterSameValueKeys=[B, A, C]
readB=2
afterReadKeys=[B, A, C]
afterNewKey=[B, A, C, D]
removedA=100
afterRemove=[B, C, D]
afterReinsert=[B, C, D, A]
finalMap={B=2, C=3, D=4, A=200}
nullKeyOld=null
nullableKeys=[null, X]
nullableSize=2
nullKeyNow=2
```

### 4.1. Thứ tự chèn không phải thứ tự chữ cái

`initialKeys=[B, A, C]` đúng với ba lần chèn ban đầu. `initialValues=[2, 1, 3]` là các giá trị theo cùng thứ tự ánh xạ, không được sắp xếp theo độ lớn.

### 4.2. Khóa bằng nhau thay cùng một ánh xạ

Lần ghi `new String("A")` trả giá trị cũ `1`, rồi map có `A=100` tại vị trí cũ:

```text
afterReplaceKeys=[B, A, C]
afterReplaceMap={B=2, A=100, C=3}
sizeAfterReplace=3
```

Không cần dùng đúng tham chiếu chuỗi đã chèn trước đó để giữ cùng khóa logic. Điều này dựa trên hợp đồng khóa của kiểu `String`.

Không nên từ đó suy ra map bắt buộc thay đối tượng khóa lưu bên trong bằng chính tham chiếu mới truyền vào. Điều đang được kiểm chứng là ánh xạ, giá trị và thứ tự của khóa logic.

### 4.3. Ghi cùng giá trị và đọc cũng không đẩy khóa xuống cuối

`put("B", 2)` trả `2` dù giá trị mới bằng giá trị cũ. Nó vẫn không chuyển `B` xuống cuối.

`get("B")` đọc giá trị hiện tại và giữ thứ tự trong chế độ chèn. Không có quy tắc “khóa vừa dùng được đưa xuống cuối” cho chế độ mặc định này.

### 4.4. Khóa mới nối cuối; khóa xóa rồi thêm lại cũng nối cuối

Thêm `D` tạo `[B, A, C, D]`. Xóa `A` để lại `[B, C, D]`. Chèn lại `A` tạo `[B, C, D, A]`.

Giá trị cuối của `A` là `200`, nhưng vị trí cuối đến từ việc ánh xạ đã bị xóa rồi được tạo mới. Không phải mọi lần cập nhật giá trị `200` đều mang cùng tác động lên thứ tự.

### 4.5. Giá trị cũ null không có nghĩa khóa chưa có

Map `nullable` có ánh xạ khóa null với giá trị null trước khi thêm `X`. Lần `put(null, 2)` trả null nhưng vẫn là thay giá trị của ánh xạ đã tồn tại:

```text
nullableKeys=[null, X]
nullableSize=2
nullKeyNow=2
```

Khóa null giữ vị trí trước `X`. Việc nhận kết quả cũ null không đủ để kết luận đây là lần chèn một khóa mới. Nếu cần phân biệt có ánh xạ hay chưa, phải xét sự tồn tại của khóa, không chỉ nhìn `get` hoặc giá trị cũ trả về.

## 5. Bảng hành vi ở chế độ thứ tự chèn

Bảng sau giả sử một `LinkedHashMap` sửa được, thao tác hợp lệ và không có nơi khác thay đổi map:

| Thao tác | Giá trị có thể đổi không? | Thứ tự của khóa đã có |
|---|---|---|
| `put(k, newValue)` khi `k` đang có | Có | Giữ nguyên |
| `put(k, sameValue)` khi `k` đang có | Có thể không đổi về nghĩa dữ liệu | Giữ nguyên |
| `get(k)` | Không thay ánh xạ | Giữ nguyên |
| `replace(k, newValue)` khi thay được | Có | Giữ nguyên |
| `entry.setValue(newValue)` trên entry hợp lệ | Có | Giữ nguyên |
| Thêm một khóa mới | Có ánh xạ mới | Khóa mới ở cuối |
| Xóa một khóa | Mất ánh xạ | Khóa không còn vị trí |
| Chèn lại khóa đã bị xóa | Có ánh xạ mới | Ở cuối tại lần chèn lại |

Những phương thức tính/cập nhật khác cũng cần được đọc theo hiệu ứng thật của chúng. Nếu kết quả làm **xóa** ánh xạ, không thể coi đó là một lần “chỉ thay giá trị” rồi mặc định vị trí sẽ được giữ cho tương lai.

Nếu giá trị là một đối tượng khả biến, sửa nội dung đối tượng đó không tự thay vị trí của khóa trong map. Đó là thay dữ liệu của đối tượng giá trị, khác với thêm hoặc xóa ánh xạ.

## 6. putAll: giữ vị trí khóa cũ, nối các khóa mới theo lượt duyệt nguồn

Với map đích theo thứ tự chèn, có thể hiểu `putAll(source)` theo hai nhóm:

1. Khóa nguồn đã có ở đích: thay giá trị, giữ vị trí của đích.
2. Khóa nguồn chưa có ở đích: tạo ánh xạ mới, nối cuối theo thứ tự mà nguồn cung cấp các ánh xạ.

Ví dụ:

```text
Đích trước:       B → A → C
Nguồn duyệt:      A → E → D

Đích sau putAll:  B → A → C → E → D
```

`A` đã có nên không được chuyển ra cuối trước `E`, `D`. Chỉ hai khóa mới nối vào sau chuỗi cũ.

Điều này có ích khi một cấu hình nền đã có thứ tự hiển thị, rồi một tập cập nhật ghi đè một số giá trị và bổ sung mục mới. Nó không tự sắp xếp toàn bộ đích theo thứ tự của nguồn.

### Nguồn cần có thứ tự được xác định nếu thứ tự mục mới là yêu cầu

Nếu nguồn là một `LinkedHashMap` mặc định và được giữ ổn định, có thể dùng thứ tự nguồn để dự đoán các khóa mới nối vào.

Nếu nguồn là `HashMap`, không được suy rằng các khóa sẽ được lấy theo thứ tự lịch sử các lần `put` của nguồn. Đích chỉ tiếp nhận thứ tự duyệt mà nguồn đang cung cấp, không thể tự khôi phục một lịch sử chưa được giữ.

Cũng không nên dùng một `Map.of` có nhiều mục rồi lấy thứ tự các đối số làm một cam kết thứ tự duyệt. Nếu thứ tự là dữ liệu cần giữ, hãy chọn nguồn và quy trình xây nguồn có hợp đồng phù hợp.

## 7. Chương trình đầy đủ: putAll và bản chép có thứ tự

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapPutAllCopyDemo {
    public static void main(String[] args) {
        Map<String, Integer> target = new LinkedHashMap<>();
        target.put("B", 2);
        target.put("A", 1);
        target.put("C", 3);

        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("A", 10);
        source.put("E", 5);
        source.put("D", 4);

        target.putAll(source);
        System.out.println("sourceOrder=" + source.keySet());
        System.out.println("targetOrder=" + target.keySet());
        System.out.println("targetValues=" + target.values());
        System.out.println("targetMap=" + target);

        Map<String, Integer> copied = new LinkedHashMap<>(target);
        target.put("A", 100);
        target.put("F", 6);
        System.out.println("sourceMapAfterChange=" + target.keySet());
        System.out.println("copyOrder=" + copied.keySet());
        System.out.println("copyA=" + copied.get("A"));
        System.out.println("sourceA=" + target.get("A"));

        Map<String, Integer> unordered = new HashMap<>();
        unordered.put("orange", 1);
        unordered.put("apple", 2);
        unordered.put("banana", 3);

        List<String> observedOrder = new ArrayList<>(unordered.keySet());
        Map<String, Integer> fromUnordered = new LinkedHashMap<>(unordered);
        System.out.println("copyMatchesObservedSourceOrder="
                + new ArrayList<>(fromUnordered.keySet()).equals(observedOrder));
    }
}
```

Lưu thành `LinkedHashMapPutAllCopyDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapPutAllCopyDemo.java
java LinkedHashMapPutAllCopyDemo
```

Đầu ra chính xác:

```text
sourceOrder=[A, E, D]
targetOrder=[B, A, C, E, D]
targetValues=[2, 10, 3, 5, 4]
targetMap={B=2, A=10, C=3, E=5, D=4}
sourceMapAfterChange=[B, A, C, E, D, F]
copyOrder=[B, A, C, E, D]
copyA=10
sourceA=100
copyMatchesObservedSourceOrder=true
```

### 7.1. Thứ tự khóa cũ thuộc đích

Nguồn có thứ tự `[A, E, D]`, còn đích sau chép là `[B, A, C, E, D]`. `A` nhận giá trị `10` ở vị trí cũ. `E` và `D` được thêm ở cuối theo thứ tự nguồn.

Các giá trị `[2, 10, 3, 5, 4]` thuộc các khóa theo chính thứ tự mới ấy.

### 7.2. Constructor chép giữ thứ tự quan sát ở thời điểm chép

`new LinkedHashMap<>(target)` tạo map mới với các ánh xạ theo thứ tự mà nguồn được duyệt lúc chép. Sau đó nguồn thay `A` thành `100` và thêm `F`; bản chép vẫn giữ chuỗi khóa cũ cùng giá trị `A=10`.

Bản chép không phải view sống của nguồn. Đây là chép cấu trúc ánh xạ, không phải sao chép sâu mọi đối tượng khóa hoặc giá trị.

### 7.3. Chép HashMap không khôi phục lịch sử chèn

Phần cuối ghi lại thứ tự đang quan sát từ `HashMap`, sau đó chép ngay sang `LinkedHashMap` trong khi nguồn không bị thay đổi.

`copyMatchesObservedSourceOrder=true` nói bản chép giữ thứ tự đã được nguồn cung cấp ở lượt đó. Chương trình không in hoặc khẳng định một thứ tự chữ cái hay thứ tự chèn cụ thể của `HashMap`.

Tạo đích có thứ tự giúp duy trì một chuỗi từ thời điểm chép trở đi. Nó không bổ sung ngược dữ liệu lịch sử mà nguồn không bảo đảm.

## 8. Thứ tự được quan sát qua các view và forEach

Với một map đang giữ thứ tự `B → A → C`:

| Cách duyệt | Dữ liệu quan sát |
|---|---|
| `keySet()` | Khóa theo thứ tự `B`, `A`, `C` |
| `values()` | Giá trị ứng với `B`, rồi `A`, rồi `C` |
| `entrySet()` | Các cặp ánh xạ theo thứ tự đó |
| `Map.forEach` | Hành động được thực hiện trên các ánh xạ theo thứ tự duyệt đã xác định |

Thay giá trị của `A` làm phần giá trị tương ứng thay đổi khi duyệt `values` hoặc `entrySet`, nhưng không đẩy vị trí của `A` ra nơi khác trong chế độ chèn.

`keySet` có kiểu `Set` không có nghĩa iterator của nó buộc phải không có thứ tự. Một set view có thể duyệt theo thứ tự được map hỗ trợ, trong khi định nghĩa bằng nhau của `Set` vẫn không xét thứ tự. Đây là hai khía cạnh khác nhau.

### View sống khác danh sách đã chép

Giả sử đã lưu một view khóa và một danh sách riêng:

```java
// Minh họa với first là LinkedHashMap theo thứ tự chèn.
Set<String> keysView = first.keySet();
List<String> copiedKeys = new ArrayList<>(keysView);
```

Khi thêm khóa mới vào map rồi bắt đầu một lượt duyệt mới:

- `keysView` phản ánh khóa mới.
- `copiedKeys` không tự có phần tử mới vì nó là danh sách đã chép.

Tương tự, view giá trị nhìn thấy giá trị vừa thay. Không nên gọi một view là “ảnh chụp của thứ tự lúc lấy view”.

Các câu trên không cho phép tùy ý thay đổi cấu trúc trong khi một iterator cũ đang hoạt động. View sống và quyền sửa trong lúc duyệt là hai vấn đề riêng.

### Thay giá trị khi đang duyệt

Trong chế độ chèn, chỉ thay giá trị của khóa đang có không được coi là thay đổi cấu trúc thứ tự như thêm/xóa ánh xạ. Khi đang duyệt `entrySet`, cách trực tiếp là dùng `entry.setValue` trên entry hợp lệ mà hiện thực hỗ trợ.

Không dùng điều này để suy rằng có thể `remove` rồi `put` bên ngoài iterator ngay trong vòng lặp. Chuỗi đó sửa cấu trúc và thay đổi vị trí. Nếu cần xóa phần tử hiện tại khi duyệt, dùng cơ chế xóa của chính iterator khi được hỗ trợ.

## 9. Map.equals không kiểm tra thứ tự chèn

Hai map có thể chứa cùng ánh xạ nhưng duyệt theo hai thứ tự khác nhau:

```text
Map thứ nhất: B → A → C
Map thứ hai: C → A → B

Mỗi khóa ở cả hai map vẫn có cùng giá trị tương ứng.
```

Theo hợp đồng chung, `Map.equals` xét các ánh xạ chứ không thêm thứ tự chèn vào tiêu chí bằng nhau. Mã băm của map cũng không phải một phép mã hóa riêng của thứ tự duyệt.

Vì thế muốn kiểm tra kết quả có đúng thứ tự hay không, hãy kiểm tra một chuỗi có xét thứ tự, chẳng hạn danh sách khóa:

```java
// Minh họa với hai map ổn định trong khi so sánh.
boolean sameMappings = first.equals(second);
boolean sameKeyOrder =
        new ArrayList<>(first.keySet())
                .equals(new ArrayList<>(second.keySet()));
```

| Phép so | Điều được so |
|---|---|
| `first.equals(second)` | Các ánh xạ khóa–giá trị |
| `first.keySet().equals(second.keySet())` | Tập khóa, không xét thứ tự |
| `first.entrySet().equals(second.entrySet())` | Tập cặp ánh xạ, không xét thứ tự |
| So hai `ArrayList` chép từ `keySet` | Chuỗi khóa theo thứ tự |

Nếu yêu cầu là vừa cùng dữ liệu vừa cùng thứ tự, phải xét cả hai khía cạnh. Đừng chỉ so `keySet` như một set rồi cho rằng thứ tự đã được kiểm chứng.

Cũng không mặc định một `Collection` giá trị bất kỳ có phép `equals` giống `List` để so chuỗi. Tạo rõ kiểu danh sách khi mục đích là kiểm tra thứ tự phần tử.

## 10. Chương trình đầy đủ: view, thay giá trị và kiểm tra thứ tự

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class LinkedHashMapViewsEqualityDemo {
    public static void main(String[] args) {
        Map<String, Integer> first = new LinkedHashMap<>();
        first.put("B", 2);
        first.put("A", 1);
        first.put("C", 3);

        Set<String> keysView = first.keySet();
        Collection<Integer> valuesView = first.values();
        List<String> copiedKeys = new ArrayList<>(keysView);

        first.put("A", 10);
        System.out.println("keysAfterUpdate=" + keysView);
        System.out.println("valuesAfterUpdate=" + valuesView);

        List<String> lines = new ArrayList<>();
        first.forEach((key, value) -> lines.add(key + "=" + value));
        System.out.println("forEachLines=" + lines);

        for (Map.Entry<String, Integer> entry : first.entrySet()) {
            if (entry.getKey().equals("B")) {
                Integer old = entry.setValue(20);
                System.out.println("entryOld=" + old);
            }
        }
        System.out.println("afterEntryUpdate=" + first);

        Map<String, Integer> reversed = new LinkedHashMap<>();
        reversed.put("C", 3);
        reversed.put("A", 10);
        reversed.put("B", 20);
        System.out.println("sameMappings=" + first.equals(reversed));
        System.out.println("sameMapHash="
                + (first.hashCode() == reversed.hashCode()));
        System.out.println("sameKeyOrder="
                + new ArrayList<>(first.keySet()).equals(
                        new ArrayList<>(reversed.keySet())));

        first.put("D", 4);
        System.out.println("liveKeysAfterAppend=" + keysView);
        System.out.println("liveValuesAfterAppend=" + valuesView);
        System.out.println("copiedKeys=" + copiedKeys);
    }
}
```

Lưu thành `LinkedHashMapViewsEqualityDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapViewsEqualityDemo.java
java LinkedHashMapViewsEqualityDemo
```

Đầu ra chính xác:

```text
keysAfterUpdate=[B, A, C]
valuesAfterUpdate=[2, 10, 3]
forEachLines=[B=2, A=10, C=3]
entryOld=2
afterEntryUpdate={B=20, A=10, C=3}
sameMappings=true
sameMapHash=true
sameKeyOrder=false
liveKeysAfterAppend=[B, A, C, D]
liveValuesAfterAppend=[20, 10, 3, 4]
copiedKeys=[B, A, C]
```

### 10.1. Giá trị đổi tại vị trí tương ứng

Sau khi cập nhật `A` thành `10`:

```text
keysAfterUpdate=[B, A, C]
valuesAfterUpdate=[2, 10, 3]
forEachLines=[B=2, A=10, C=3]
```

Thứ tự khóa giữ nguyên, giá trị của ánh xạ thứ hai đổi. Các dòng thu qua `forEach` tuân theo cùng trật tự.

Lượt duyệt entry tiếp theo thay giá trị `B` bằng `entry.setValue(20)`; phương thức trả giá trị cũ `2`. Sau đó map vẫn theo thứ tự `B, A, C`.

### 10.2. Hai map bằng nhau nhưng chuỗi khóa khác nhau

Map `reversed` được chèn theo thứ tự `C, A, B` và có cùng ánh xạ với map `first`. Kết quả:

```text
sameMappings=true
sameMapHash=true
sameKeyOrder=false
```

Ba dòng cùng đúng, không có mâu thuẫn. Chúng đang kiểm tra các khía cạnh khác nhau của dữ liệu.

### 10.3. View phản ánh lần thêm sau

Thêm `D` làm view khóa thành `[B, A, C, D]`, view giá trị thành `[20, 10, 3, 4]`. Danh sách `copiedKeys` vẫn là `[B, A, C]`.

Không có một iterator đang mở bị sửa từ ngoài trong ví dụ; chương trình thay đổi map giữa các lượt quan sát rồi duyệt lại view.

## 11. Chế độ thứ tự truy cập là một lựa chọn khác

`LinkedHashMap` còn có constructor cho phép chọn thứ tự truy cập:

```java
// Minh họa cách tạo; chưa phải chương trình độc lập.
Map<String, Integer> insertion = new LinkedHashMap<>();
Map<String, Integer> access =
        new LinkedHashMap<>(16, 0.75f, true);
```

Tham số thứ ba `accessOrder` có ý nghĩa:

| Giá trị | Chế độ |
|---|---|
| `false` | Thứ tự chèn |
| `true` | Thứ tự truy cập |

Các constructor thông thường không chọn `true` tạo map theo thứ tự chèn. Trong chế độ truy cập, một số lời gọi như `get` và `put` được tính là truy cập vào entry; khóa có thể được chuyển về phía cuối theo quy tắc của chế độ này.

Vì vậy phát biểu “ghi lại khóa không đổi thứ tự” trong bài phải gắn với **chế độ chèn và thao tác put thông thường**. Không áp nguyên xi cho một đối tượng đã được tạo theo `accessOrder=true`.

### Chương trình đầy đủ đối chiếu hai chế độ

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapOrderModesDemo {
    public static void main(String[] args) {
        Map<String, Integer> insertion = new LinkedHashMap<>();
        Map<String, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);

        int value = 1;
        for (String key : List.of("A", "B", "C")) {
            insertion.put(key, value);
            access.put(key, value);
            value++;
        }

        System.out.println("insertionBefore=" + insertion.keySet());
        System.out.println("accessBefore=" + access.keySet());

        insertion.put("B", 20);
        access.put("B", 20);
        System.out.println("insertionAfterPutB=" + insertion.keySet());
        System.out.println("accessAfterPutB=" + access.keySet());

        insertion.get("A");
        access.get("A");
        System.out.println("insertionAfterGetA=" + insertion.keySet());
        System.out.println("accessAfterGetA=" + access.keySet());
    }
}
```

Lưu thành `LinkedHashMapOrderModesDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapOrderModesDemo.java
java LinkedHashMapOrderModesDemo
```

Đầu ra chính xác:

```text
insertionBefore=[A, B, C]
accessBefore=[A, B, C]
insertionAfterPutB=[A, B, C]
accessAfterPutB=[A, C, B]
insertionAfterGetA=[A, B, C]
accessAfterGetA=[C, B, A]
```

### Cùng lời gọi, khác chính sách thứ tự

Hai map cùng bắt đầu với `[A, B, C]`.

Sau `put("B", 20)`:

- Map thứ tự chèn vẫn `[A, B, C]`.
- Map thứ tự truy cập thành `[A, C, B]`.

Sau `get("A")`:

- Map thứ tự chèn vẫn `[A, B, C]`.
- Map thứ tự truy cập thành `[C, B, A]`.

Khác biệt không do giá trị `20` lớn hơn hay nhỏ hơn các giá trị khác. Nó đến từ chế độ được chọn khi tạo map.

Đừng tự dùng thứ tự truy cập như thể đó là “thứ tự lần sửa gần nhất” nếu ứng dụng còn đọc dữ liệu: một phép đọc cũng có thể làm thay đổi thứ tự. Hãy xác định rõ sự kiện nào trong nghiệp vụ phải ảnh hưởng vị trí.

### Cẩn thận khi đưa get vào vòng duyệt

Trong chế độ chèn, `get` không chuyển khóa theo thứ tự truy cập. Trong chế độ truy cập, lời gọi đọc có thể thay chính thứ tự đang duyệt.

Nếu đã có entry trong tay, đọc `entry.getValue()` thể hiện ý định trực tiếp hơn so với lại gọi `map.get(entry.getKey())`. Không được suy rằng mọi lời gọi đọc trên mọi map đều không có ảnh hưởng tới trạng thái thứ tự.

## 12. Khi muốn chủ động chuyển một khóa xuống cuối

Với API Java 17 và một map theo thứ tự chèn, xóa rồi chèn lại là một cách tạo thứ tự mới. Nhưng phải biết đó là hai thao tác riêng, không chỉ là đổi giá trị.

Đoạn minh họa dưới giả sử `numbers` là `LinkedHashMap<String, Integer>` theo thứ tự chèn, sửa được, do một luồng sở hữu và không có iterator đang mở:

```java
String key = "A";
if (numbers.containsKey(key)) {
    Integer value = numbers.remove(key);
    numbers.put(key, value);
}
```

Kiểm tra sự tồn tại có mục đích: nếu khóa có giá trị null thì vẫn cần giữ ánh xạ khi chuyển vị trí. Chỉ viết `if (value != null)` sau `remove` có thể làm mất một ánh xạ null. Ngược lại, xóa một khóa vốn không có rồi vô điều kiện `put` kết quả null có thể vô tình tạo thêm ánh xạ.

Cặp xóa–chèn lại có các giới hạn cần hiểu:

- Nó thay đổi cấu trúc map và vị trí duyệt.
- Nó không tự là giao dịch nguyên tử cho nhiều luồng.
- Nếu có ngoại lệ hoặc quy tắc riêng về thay đổi dữ liệu, ứng dụng cần xử lý theo yêu cầu của mình.
- Không thực hiện tùy ý giữa một vòng `for-each` đang duyệt map; thay đổi cấu trúc ngoài iterator có thể vi phạm hợp đồng duyệt.

Các iterator fail-fast có thể phát hiện sai sử dụng bằng `ConcurrentModificationException`, nhưng không được dựa vào việc một lần chạy không có ngoại lệ để kết luận cách sửa trong lúc duyệt là hợp lệ. Việc giữ thứ tự dự đoán được cũng không làm `LinkedHashMap` trở thành cấu trúc tự đồng bộ cho nhiều luồng.

### Ranh giới phiên bản: phương thức đặt vị trí tường minh

Từ Java 21, `LinkedHashMap` có các API như `putFirst` và `putLast` để đặt vị trí tường minh, có thể đổi vị trí của entry đã có. Chúng khác `put` thông thường. Quy tắc của từng phương thức phải được đọc theo API tương ứng.

Các chương trình chạy đầy đủ trong bài dùng API tương thích Java 17; phần nhắc này giúp tránh khái quát thành “không có thao tác nào trên LinkedHashMap có thể đổi vị trí khóa đã tồn tại”.

## 13. Áp dụng vào dữ liệu cập nhật nhiều lần

Một tình huống thường gặp là cần giữ thứ tự xuất hiện của các mã trường nhưng dùng giá trị cuối cùng của từng mã:

```text
Các lần cập nhật:
B=1, A=2, B=3, C=4, A=5

Thứ tự chèn của các khóa còn tồn tại:
B → A → C

Giá trị cuối cùng:
B=3, A=5, C=4
```

Chỉ cần gọi `put` cho từng lần cập nhật vào map theo thứ tự chèn, ta giữ vị trí ban đầu của từng khóa đang tồn tại và thay giá trị khi khóa đó xuất hiện lại.

Điều này **không giữ toàn bộ lịch sử thay đổi**. Các giá trị trước của cùng khóa bị thay; nếu cần nhật ký mọi lần sửa, phải lưu lịch sử ở một cấu trúc phù hợp khác.

Nó cũng không tự tạo thứ tự “sửa gần nhất”: ở ví dụ, `A` được cập nhật cuối nhưng không chuyển thành khóa cuối.

### Từ nơi tạo dữ liệu đến nơi dùng dữ liệu

Khai báo:

```java
Map<String, Integer> data = new LinkedHashMap<>();
```

không làm mất hành vi thứ tự của đối tượng `LinkedHashMap` đang tồn tại. Kiểu biến là `Map`, còn đối tượng thực vẫn giữ chính sách thứ tự đã chọn.

Tuy nhiên, một phương thức chỉ hứa trả `Map` bất kỳ thì người gọi không nên tự giả định mọi hiện thực đều giữ thứ tự chèn. Nếu thứ tự là yêu cầu của giao tiếp giữa các phần, hãy mô tả rõ nó trong hợp đồng.

Nếu chuyển dữ liệu qua một bước trung gian, cũng phải xem bước đó có giữ thứ tự không. Chẳng hạn, `Map.copyOf` không cung cấp cam kết giữ thứ tự chèn chỉ vì nguồn là `LinkedHashMap`. Một bản chép bằng `LinkedHashMap` và một map không cho sửa từ factory có các hợp đồng khác nhau.

Khi xuất các dòng báo cáo hoặc xây giao diện, cần để quá trình tiêu thụ đi theo thứ tự đã giữ. Việc chọn đúng cấu trúc nguồn chưa đủ nếu bước sau tự sắp xếp hoặc đổi sang một cấu trúc không hứa giữ thứ tự.

## 14. Lỗi thường gặp

| Cách hiểu sai | Cách hiểu theo đúng chế độ chèn |
|---|---|
| Khóa được ghi lại sẽ tự xuống cuối | `put` vào khóa đang có giữ vị trí |
| Giá trị lớn hơn sẽ được đẩy về sau | Không tự sắp xếp theo giá trị |
| Chèn B, A, C sẽ duyệt A, B, C | Duyệt B, A, C theo thứ tự chèn |
| Xóa rồi chèn lại trở về vị trí lịch sử cũ | Chèn lại tạo vị trí mới ở cuối |
| Giá trị cũ trả về null nghĩa là khóa mới | Có thể khóa cũ đã mang giá trị null |
| Map.equals đủ kiểm tra thứ tự | Nó xét ánh xạ; dùng thêm phép so chuỗi |
| keySet là Set nên không thể có thứ tự duyệt | View vẫn có iterator theo thứ tự map hỗ trợ |
| Chép HashMap sang LinkedHashMap phục hồi thứ tự các lần put cũ | Chỉ giữ thứ tự nguồn cung cấp lúc chép |
| LinkedHashMap luôn dùng thứ tự chèn trong mọi cấu hình | Có chế độ thứ tự truy cập được chọn riêng |
| Có thứ tự đồng nghĩa có API truy cập theo chỉ số | `get` vẫn nhận khóa |

## 15. Tự kiểm tra bằng chuỗi thao tác

Các câu dưới giả sử map theo thứ tự chèn, không có thao tác định vị tường minh hay chính sách tự loại bỏ entry.

### Câu 1: Thay giá trị ở giữa

Map có thứ tự `A, B, C`. Gọi `put("B", 99)`. Thứ tự và kích thước có đổi không?

**Đáp án:** Thứ tự vẫn `A, B, C`; kích thước không tăng. Giá trị của `B` đổi thành `99`.

### Câu 2: Ghi cùng giá trị

`B` đang có giá trị `99`; gọi lại `put("B", 99)`. Có phải khóa bị đưa xuống cuối vì đây là một lần ghi mới không?

**Đáp án:** Không. Khóa logic đã tồn tại, nên không tạo vị trí mới trong thứ tự chèn.

### Câu 3: Đối tượng khóa mới nhưng equals

Map chứa khóa chuỗi `"B"`. Gọi `put(new String("B"), 7)`. Có chắc thêm một vị trí thứ hai cho B không?

**Đáp án:** Không. Hai chuỗi bằng nhau theo nội dung nên là cùng khóa logic, với hợp đồng băm nhất quán của `String`.

### Câu 4: Xóa rồi chèn

Map theo thứ tự `A, B, C`; xóa `B`, rồi chèn lại `B`. Thứ tự cuối là gì?

**Đáp án:** `A, C, B`. Vị trí cũ không được dành lại sau khi ánh xạ bị xóa.

### Câu 5: Khóa mới

Map theo thứ tự `C, A`. Thêm khóa mới `B`. Có tự thành `A, B, C` không?

**Đáp án:** Không. Kết quả là `C, A, B`. Thứ tự chèn khác thứ tự chữ cái.

### Câu 6: putAll

Đích có `A, B`; nguồn duyệt `B, D, C`. Cả hai là các map phù hợp và ổn định. Thứ tự khóa cuối ở đích là gì?

**Đáp án:** `A, B, D, C`. B giữ vị trí và nhận giá trị mới; D, C là khóa mới nối cuối theo nguồn.

### Câu 7: Ánh xạ có giá trị null

Khóa `A` đang có giá trị null trước `B`. Gọi `put("A", 1)` trả null. A có phải xuống cuối không?

**Đáp án:** Không. A đã có ánh xạ; giá trị cũ null không biến lần thay giá trị thành lần tạo khóa mới.

### Câu 8: So hai map khác thứ tự

Hai map có cùng ánh xạ, nhưng chuỗi khóa lần lượt là `A, B` và `B, A`. `Map.equals` có thể true không?

**Đáp án:** Có. Để kiểm tra thứ tự, so thêm các danh sách khóa theo thứ tự duyệt.

### Câu 9: Tham số accessOrder

Map được tạo bằng `new LinkedHashMap<>(16, 0.75f, true)`. Có dùng nguyên quy tắc “get không đổi thứ tự” của chế độ mặc định cho nó được không?

**Đáp án:** Không. Đây là chế độ thứ tự truy cập; `get` có thể làm thay đổi thứ tự.

### Câu 10: Bản chép từ HashMap

Bản chép `LinkedHashMap` khớp với lượt duyệt hiện tại của nguồn `HashMap`. Có chứng minh nó đã giữ lịch sử chèn ban đầu của nguồn không?

**Đáp án:** Không. Nguồn không hứa lịch sử đó qua thứ tự duyệt; bản chép chỉ giữ thứ tự được cung cấp lúc chép.

## 16. Thực hành: giữ vị trí, cập nhật nội dung

Viết một chương trình dùng `LinkedHashMap<String, Integer>` mặc định, thực hiện lần lượt:

```text
put("name", 1)
put("price", 2)
put("stock", 3)
put("price", 20)
put("category", 4)
remove("name")
put("name", 10)
```

Trước khi chạy, dự đoán:

1. Chuỗi khóa sau mỗi thao tác.
2. Giá trị cũ trả về từ lần thay `price`.
3. Giá trị cũ trả về từ lần xóa `name`.
4. Chuỗi khóa và giá trị cuối.
5. Một phép so cụ thể để kiểm tra đúng thứ tự, ngoài kiểm tra ánh xạ.

**Đáp án mốc cuối:**

```text
Khóa: [price, stock, category, name]
Giá trị: [20, 3, 4, 10]
Giá trị cũ khi thay price: 2
Giá trị cũ khi xóa name: 1
Kích thước cuối: 4
```

Mở rộng bằng một map cập nhật có thứ tự nguồn `stock, note, color`. Gọi `putAll`, dự đoán khóa nào giữ vị trí và khóa nào nối cuối, rồi xác nhận bằng danh sách khóa.

Cuối cùng tạo một map thứ hai có cùng ánh xạ nhưng chèn theo thứ tự khác. Kiểm tra `Map.equals` và phép so danh sách khóa riêng biệt. Giải thích vì sao kiểm tra dữ liệu và kiểm tra thứ tự đều cần thiết nếu cả hai là yêu cầu của đầu ra.

## Tài liệu đối chiếu

- [Java 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự chèn, ghi lại khóa đã có, constructor chép, các view và chế độ thứ tự truy cập.
- [Java 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): khóa logic, `put`, `putAll`, `forEach`, `equals` và hợp đồng các factory.
- [Java 21 — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): các thao tác đặt vị trí tường minh như `putFirst`, `putLast`, để phân biệt với `put` thông thường.

Bốn chương trình độc lập được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy kiểm chứng trên JDK 24.0.2. Chúng chỉ dùng API tương thích Java 17; các khối đầu ra là kết quả thực tế.
