# Thứ tự duyệt và quy tắc null của EnumMap

## 1. EnumMap gắn một giá trị với mỗi khóa enum đang có mặt

`EnumMap<K, V>` là một implementation của `Map` chuyên dùng khi khóa thuộc cùng một kiểu enum. Khóa xác định loại mục, còn giá trị có thể là kiểu dữ liệu khác phù hợp với `V`.

Ví dụ:

```java
enum Metric {
    CPU, MEMORY, DISK, NETWORK
}
```

Một `EnumMap<Metric, String>` có thể lưu thông tin cho một số metric:

```java
java.util.EnumMap<Metric, String> states = new java.util.EnumMap<>(Metric.class);
states.put(Metric.DISK, "ok");
states.put(Metric.CPU, "ready");
states.put(Metric.MEMORY, null);
```

Các câu lệnh trên đặt trong một phương thức dùng được enum mẫu. Map chỉ có ba ánh xạ đã được thêm; `NETWORK` không tự xuất hiện vì enum có hằng đó.

Hai đặc điểm quan trọng của `EnumMap` là thứ tự duyệt theo khai báo enum và quy tắc null khác nhau giữa khóa với giá trị. Những đặc điểm này vẫn áp dụng trong Java hiện hành; chương trình đầy đủ bên dưới chạy với Java 17 trở lên.

## 2. Thứ tự duyệt theo thứ tự khai báo khóa enum

Với khai báo `Metric` ở trên, thứ tự các khóa đang có mặt là:

```text
CPU → MEMORY → DISK
```

Dù `DISK` được thêm đầu tiên, nó vẫn đứng sau `CPU` và `MEMORY` khi duyệt. Đây cũng không phải sắp xếp tên theo chữ cái: thứ tự do vị trí các hằng trong khai báo enum quyết định.

Có thể quan sát qua ba góc nhìn collection:

```java
System.out.println(states.keySet());
System.out.println(states.values());
System.out.println(states.entrySet());
```

Với dữ liệu mẫu, kết quả:

```text
[CPU, MEMORY, DISK]
[ready, null, ok]
[CPU=ready, MEMORY=null, DISK=ok]
```

- `keySet()` duyệt các khóa theo thứ tự khai báo enum.
- `values()` duyệt các giá trị ứng với cùng thứ tự khóa ấy; nó không tự sắp xếp giá trị.
- `entrySet()` duyệt các cặp khóa–giá trị theo thứ tự khóa.

Chỉ những khóa thực sự có ánh xạ mới xuất hiện. `NETWORK` vắng mặt, còn `MEMORY` vẫn xuất hiện vì nó đang có một ánh xạ hợp lệ tới giá trị null.

Thêm lại một khóa đã tồn tại bằng `put` thay giá trị của khóa đó, không biến nó thành một mục “mới nhất ở cuối” như một cách ghi nhật ký thứ tự thêm. Xóa rồi thêm lại khóa cũng không đổi quy tắc thứ tự của `EnumMap`.

## 3. Duyệt entry khi cần dùng cả khóa lẫn giá trị

```java
for (java.util.Map.Entry<Metric, String> entry : states.entrySet()) {
    Metric metric = entry.getKey();
    String state = entry.getValue();
    System.out.println(metric + "=" + state);
}
```

Đây là vòng lặp minh họa đặt trong một phương thức đã có biến `states`. `entry.getValue()` có thể trả null, nên không gọi ngay `state.length()` hoặc `state.toUpperCase()` nếu hợp đồng của map cho phép giá trị null.

Nếu muốn hiển thị cả các metric chưa có ánh xạ, duyệt `Metric.values()` và kiểm tra từng khóa. Đó là một yêu cầu khác với duyệt `entrySet`, vì `values()` của enum liệt kê toàn bộ miền khóa còn `entrySet` chỉ liệt kê các ánh xạ đang tồn tại.

Không tự dùng `ordinal()` để tra một mảng giá trị riêng rồi coi nó như hợp đồng dữ liệu ổn định. `EnumMap` đã quản lý ánh xạ theo khóa enum; thứ tự khai báo là quy tắc duyệt, không phải một mã lưu trữ nghiệp vụ cần sao chép ra ngoài.

## 4. Khóa null bị cấm, nhưng truy vấn null không đồng nghĩa với chèn

```java
// states.put(null, "unknown"); // Ném NullPointerException khi chạy.
```

Một khóa phải là hằng của kiểu enum phù hợp; null không trở thành một “metric chưa biết” trong map. Nếu ứng dụng cần một loại khóa đặc biệt, hãy mô hình hóa theo yêu cầu thật thay vì dùng khóa null để thay thế.

Tuy nhiên, `EnumMap` cho phép các thao tác truy vấn hoặc xóa bằng khóa null mà không chèn nó:

```java
boolean present = states.containsKey(null); // false
String value = states.get(null);            // null
String removed = states.remove(null);       // null
```

Các kết quả trên không có nghĩa map đang chứa một khóa null. Chúng cho biết không có ánh xạ phù hợp để tìm hoặc xóa.

Vì vậy, câu “EnumMap không cho null” là thiếu chính xác. Quy tắc cần đọc theo vai trò và thao tác: chèn khóa null bị từ chối, truy vấn khóa null có kết quả không tìm thấy, còn giá trị null lại được phép.

## 5. Giá trị null là một ánh xạ thật sự

```java
states.put(Metric.MEMORY, null);
boolean present = states.containsKey(Metric.MEMORY); // true
String value = states.get(Metric.MEMORY);            // null
```

Map có thể chứa giá trị null cho một khóa hợp lệ. Khóa đó được tính trong `size`, xuất hiện trong `keySet` và có một entry khi duyệt.

So sánh hai trạng thái:

| Trạng thái của khóa | `get(key)` | `containsKey(key)` |
| --- | --- | --- |
| Không có ánh xạ | `null` | `false` |
| Có ánh xạ tới null | `null` | `true` |
| Có ánh xạ tới giá trị khác null | Giá trị đã lưu | `true` |

Chỉ nhìn `get(key) == null` không phân biệt được hai hàng đầu. Nếu miền dữ liệu cần phân biệt “chưa có mục này” với “mục này được đặt giá trị thiếu”, phải kiểm tra sự hiện diện bằng `containsKey` hoặc chọn mô hình giá trị rõ ràng hơn.

`containsValue(null)` cũng hợp lệ và trả về true khi có ít nhất một ánh xạ đang giữ null. Nó không cho biết khóa nào giữ giá trị ấy; nếu cần khóa, duyệt entry theo hợp đồng đã chọn.

## 6. getOrDefault chỉ dùng mặc định khi không có ánh xạ

```java
String memory = states.getOrDefault(Metric.MEMORY, "missing");
String network = states.getOrDefault(Metric.NETWORK, "missing");
```

Với dữ liệu mẫu:

- `memory` vẫn là null vì `MEMORY` đang có ánh xạ tới null.
- `network` là `"missing"` vì `NETWORK` chưa có ánh xạ.

Không coi `getOrDefault` như một phép “thay mọi null bằng mặc định”. Nó giữ phân biệt giữa một ánh xạ có mặt và sự vắng mặt của khóa.

Điều này còn liên quan đến unboxing:

```java
java.util.EnumMap<Metric, Integer> counts = new java.util.EnumMap<>(Metric.class);
counts.put(Metric.MEMORY, null);
// int count = counts.getOrDefault(Metric.MEMORY, 0); // NullPointerException.
```

Kết quả vẫn là `Integer null`; khi gán sang `int`, Java phải unbox và gây lỗi. Nếu muốn null cũng được thay bằng một số mặc định, hãy xác định chính sách ấy rõ ràng rồi kiểm tra giá trị lấy ra. Không dựa vào tên `getOrDefault` để bỏ qua hợp đồng null.

## 7. Các thao tác cập nhật có thể xử lý null khác nhau

### computeIfAbsent xem ánh xạ null như cần tính giá trị

```java
states.put(Metric.MEMORY, null);
String loaded = states.computeIfAbsent(Metric.MEMORY, key -> "loaded");
```

Dù khóa đã có mặt, `computeIfAbsent` vẫn có thể gọi hàm cung cấp khi giá trị hiện tại là null. Trong ví dụ, nó lưu `"loaded"` và trả về giá trị đó.

Nếu hàm cung cấp trả null, phương thức không tạo một giá trị khác null mới; một ánh xạ null đã có không tự biến thành một kết quả đã tải thành công. Hợp đồng của thao tác này không giống quy tắc “chỉ lấy mặc định khi khóa vắng” của `getOrDefault`.

Ví dụ không có cập nhật đồng thời. `EnumMap` không tự cung cấp tính nguyên tử để nhiều luồng cùng dùng `computeIfAbsent` như một cơ chế chỉ tải một lần.

### Xóa ánh xạ null có thể cần kết quả boolean rõ ràng

`remove(key)` trả giá trị trước đó, nên trả null có thể là vừa xóa một ánh xạ null hoặc không tìm được khóa. Nếu muốn xóa chỉ khi ánh xạ đang có giá trị null và nhận kết quả rõ ràng:

```java
boolean removed = states.remove(Metric.MEMORY, null);
```

Overload hai đối số kiểm tra cả sự hiện diện và giá trị phù hợp, rồi trả boolean. Khi trả `true`, ánh xạ đã bị xóa. Nếu chỉ cần bỏ khóa bất kể giá trị, `remove(key)` vẫn phù hợp; đừng bắt kết quả null của nó tự mang thêm thông tin không có trong hợp đồng.

## 8. Chương trình chạy đầy đủ

Lưu thành **`EnumMapOrderAndNullDemo.java`**:

```java
import java.util.EnumMap;
import java.util.Map;

public class EnumMapOrderAndNullDemo {
    enum Metric {
        CPU, MEMORY, DISK, NETWORK
    }

    public static void main(String[] args) {
        EnumMap<Metric, String> states = new EnumMap<>(Metric.class);
        states.put(Metric.DISK, "ok");
        states.put(Metric.CPU, "ready");
        states.put(Metric.MEMORY, null);

        System.out.println("keys=" + states.keySet());
        System.out.println("values=" + states.values());
        for (Map.Entry<Metric, String> entry : states.entrySet()) {
            System.out.println(entry.getKey() + "=" + entry.getValue());
        }

        System.out.println("present null=" + states.containsKey(Metric.MEMORY));
        System.out.println("absent=" + states.containsKey(Metric.NETWORK));
        System.out.println("mapped null default="
                + states.getOrDefault(Metric.MEMORY, "missing"));
        System.out.println("absent default="
                + states.getOrDefault(Metric.NETWORK, "missing"));

        System.out.println("null key lookup=" + states.get(null));
        System.out.println("null key present=" + states.containsKey(null));
        System.out.println("null key remove=" + states.remove(null));
        try {
            states.put(null, "unknown");
        } catch (NullPointerException ex) {
            System.out.println("null key rejected");
        }

        boolean removed = states.remove(Metric.MEMORY, null);
        System.out.println("removed null mapping=" + removed
                + ", keys=" + states.keySet());

        states.put(Metric.MEMORY, null);
        String loaded = states.computeIfAbsent(Metric.MEMORY, key -> "loaded");
        System.out.println("computed=" + loaded);
        System.out.println("after compute keys=" + states.keySet());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all EnumMapOrderAndNullDemo.java
java EnumMapOrderAndNullDemo
```

Stdout chính xác:

```text
keys=[CPU, MEMORY, DISK]
values=[ready, null, ok]
CPU=ready
MEMORY=null
DISK=ok
present null=true
absent=false
mapped null default=null
absent default=missing
null key lookup=null
null key present=false
null key remove=null
null key rejected
removed null mapping=true, keys=[CPU, DISK]
computed=loaded
after compute keys=[CPU, MEMORY, DISK]
```

Dòng cuối cho thấy thêm lại `MEMORY` không đẩy nó xuống cuối thứ tự duyệt. Vị trí của khóa vẫn theo thứ tự khai báo enum.

Chương trình cũng đối chiếu trực tiếp ba điều khác nhau: truy vấn một khóa null, giữ giá trị null ở một khóa hợp lệ và từ chối thao tác chèn khóa null.

## 9. Các collection view không phải bản sao

`keySet`, `values` và `entrySet` phản ánh map phía sau. Nếu cần giữ một bản dữ liệu độc lập, không chỉ gán góc nhìn sang một biến khác rồi coi đó là bản chụp.

Ví dụ, `states.keySet().remove(Metric.CPU)` xóa cả ánh xạ `CPU` khỏi map, không chỉ xóa một dòng của một danh sách khóa độc lập. Tương tự, một số thao tác xóa được hỗ trợ qua view giá trị hoặc entry cũng tác động tới map.

Nếu cần duyệt một trạng thái ổn định do mình sở hữu, có thể tạo bản sao ánh xạ phù hợp, chẳng hạn `new EnumMap<>(states)` khi nguồn đang là EnumMap. Bản sao giữ thứ tự khóa, nhưng vẫn là sao chép nông đối với các đối tượng giá trị; một giá trị có trạng thái thay đổi không tự được nhân bản sâu.

Nếu đổi dữ liệu sang một implementation map khác, cần đọc lại hợp đồng của implementation đó. Không suy ra mọi map sao chép từ EnumMap đều giữ bảo đảm thứ tự khai báo enum hoặc cùng quy tắc null.

## 10. Iterator weakly consistent không phải snapshot hoặc bảo đảm đa luồng

Iterator của các collection view của `EnumMap` có tính nhất quán yếu (weakly consistent): nó không ném `ConcurrentModificationException` chỉ vì có sửa đổi map trong quá trình duyệt, và có thể thấy hoặc không thấy tác động của các sửa đổi ấy theo hợp đồng API.

Điều đó không có nghĩa mỗi lần duyệt là một bản chụp cố định. Không thiết kế stdout hay logic phụ thuộc vào việc một mục vừa thêm trong lúc duyệt chắc chắn xuất hiện hoặc chắc chắn không xuất hiện.

`EnumMap` cũng không tự đồng bộ hóa. Nếu nhiều luồng cùng truy cập với cập nhật, cần một chính sách truy cập và đồng bộ phù hợp. Tính weakly consistent của iterator không tự thay thế các bảo đảm về đồng bộ hóa hoặc việc công bố dữ liệu giữa các luồng.

Các ví dụ trong bài không thay đổi map trong lúc iterator đang duyệt, nên thứ tự và nội dung stdout được xác định từ trạng thái đầu vào rõ ràng.

## 11. Thiết kế hợp đồng null cho dữ liệu của ứng dụng

API cho phép giá trị null không có nghĩa ứng dụng bắt buộc phải dùng nó. Có thể chọn một trong các hợp đồng phù hợp:

- Chỉ lưu giá trị khác null; khi chưa có dữ liệu thì không có ánh xạ. Lúc đó một số thao tác đọc đơn giản hơn, nhưng phải thực sự kiểm soát mọi nơi ghi.
- Cho phép ánh xạ null có một ý nghĩa riêng, đồng thời dùng `containsKey` khi cần phân biệt với khóa vắng.
- Dùng một kiểu giá trị thể hiện rõ trạng thái như đang tải, có dữ liệu hoặc lỗi nếu miền dữ liệu có nhiều trạng thái hơn một null có thể biểu đạt rõ ràng.

Đừng tự gán ý nghĩa “không tồn tại” cho mọi kết quả null khi implementation và API của chính bạn vẫn cho phép một ánh xạ null. Tương tự, đừng dùng `getOrDefault` như cơ chế mặc định hóa khi hai trạng thái ấy cần được xử lý khác nhau.

## 12. Tự thực hành

1. Thêm các khóa theo thứ tự `NETWORK`, `DISK`, `MEMORY`, `CPU`; xác nhận thứ tự của cả ba view theo khai báo enum.
2. Đặt null cho hai khóa và bỏ hẳn một khóa. Viết hàm mô tả ba trạng thái: vắng, có null, có giá trị khác null.
3. Kiểm tra `getOrDefault` cho một khóa null-value và một khóa vắng. Sau đó viết chính sách riêng nếu muốn cả hai nhận cùng một mặc định.
4. Xóa rồi thêm lại `CPU`, quan sát vị trí duyệt của nó. Giải thích vì sao không xuất hiện như một mục mới nhất ở cuối.
5. Tạo một map có giá trị `Integer null`, thử gán kết quả đọc vào `int` và chỉ ra bước unboxing gây lỗi.

Với `EnumMap`, thứ tự đến từ khóa enum, còn ý nghĩa của null đến từ vai trò của nó và thao tác đang dùng. Đọc đúng hai quy tắc này giúp phân biệt dữ liệu vắng với dữ liệu có mặt, đồng thời dự đoán chính xác kết quả duyệt và cập nhật.

## Tài liệu đối chiếu

- [EnumMap — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html): thứ tự view, null key/value và iterator weakly consistent.
- [Map.getOrDefault](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,V)): phân biệt ánh xạ có mặt với khóa không tồn tại.
- [Map.computeIfAbsent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#computeIfAbsent(K,java.util.function.Function)): tính giá trị khi khóa vắng hoặc giá trị hiện tại null.
- [Map.remove(key, value)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#remove(java.lang.Object,java.lang.Object)): xóa có điều kiện và kết quả boolean.
