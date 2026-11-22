# Tạo Map bằng `Map.of`, `Map.entry` và `Map.ofEntries`

Từ Java 9, interface `Map` cung cấp các phương thức factory tĩnh để tạo map từ một tập cặp khóa–giá trị đã biết: `Map.of`, `Map.entry` và `Map.ofEntries`. Đây là cách gọn để khai báo dữ liệu cố định, cấu hình hoặc bảng tra cứu nhỏ mà không cần tạo `HashMap` rồi gọi `put` nhiều lần.

Các map tạo bằng những factory này là **unmodifiable**: cấu trúc map không thể được thêm, xóa hoặc thay thế ánh xạ sau khi tạo. Chúng không tự làm cho các object được lưu làm value trở thành bất biến; nếu một value là object có thể thay đổi, trạng thái bên trong object đó vẫn có thể thay đổi.

## 1. `Map.of` — tạo map từ tối đa 10 cặp khóa–giá trị

`Map.of` có các overload nhận từ 0 đến 10 cặp khóa–giá trị. Mỗi cặp được truyền theo thứ tự `key, value`:

```java
Map<String, Integer> priorities = Map.of(
    "critical", 1,
    "normal", 2,
    "low", 3
);
```

Kiểu generic `K` và `V` thường được trình biên dịch suy luận từ các đối số và kiểu đích. Ví dụ trên tạo `Map<String, Integer>` với ba ánh xạ.

Map rỗng cũng có thể được tạo bằng `Map.of()`:

```java
Map<String, Integer> empty = Map.of();
```

Vì số overload của `Map.of` dừng ở 10 cặp, không thể truyền trực tiếp 11 cặp trở lên vào một lời gọi `Map.of`. Khi cần nhiều cặp hơn, dùng `Map.ofEntries`.

## 2. `Map.entry` — tạo một entry không thể sửa đổi

`Map.entry(key, value)` tạo một đối tượng `Map.Entry<K, V>` không thể sửa đổi. Entry này hữu ích khi chuẩn bị các cặp để truyền vào `Map.ofEntries`:

```java
Map.Entry<String, Integer> archived = Map.entry("archived", 3);
```

Bạn có thể đọc `getKey()` và `getValue()` từ entry. Gọi `setValue(...)` sẽ ném `UnsupportedOperationException`. `Map.entry` không chấp nhận key hoặc value là `null`; trường hợp đó ném `NullPointerException`.

`Map.entry` chỉ tạo một entry, chưa tạo map. Để gom nhiều entry thành một map, dùng `Map.ofEntries`.

## 3. `Map.ofEntries` — tạo map từ nhiều entry

`Map.ofEntries` nhận một số lượng biến đổi các đối tượng `Map.Entry`. Đây là lựa chọn khi map có hơn 10 cặp hoặc khi các entry đã được tạo sẵn:

```java
Map<String, Integer> states = Map.ofEntries(
    Map.entry("draft", 0),
    Map.entry("archived", 3),
    Map.entry("published", 4)
);
```

Bạn có thể truyền các entry đã lưu trong biến:

```java
Map.Entry<String, Integer> archived = Map.entry("archived", 3);

Map<String, Integer> states = Map.ofEntries(
    Map.entry("draft", 0),
    archived,
    Map.entry("published", 4)
);
```

Không có giới hạn 10 cặp như các overload của `Map.of`; số entry được truyền theo dạng varargs. Mỗi phần tử phải là một `Map.Entry` hợp lệ. Truyền entry `null`, key `null` hoặc value `null` sẽ gây `NullPointerException`.

## 4. So sánh ba phương thức

| Phương thức | Kết quả | Dùng khi nào? | Giới hạn và quy tắc chính |
| --- | --- | --- | --- |
| `Map.of(...)` | Một `Map<K, V>` không thể sửa đổi | Có tối đa 10 cặp key–value và muốn viết trực tiếp, ngắn gọn | Có overload từ 0 đến 10 cặp; không chấp nhận null hoặc khóa trùng |
| `Map.entry(k, v)` | Một `Map.Entry<K, V>` không thể sửa đổi | Muốn biểu diễn một cặp key–value, thường để truyền vào `Map.ofEntries` | Chỉ tạo entry, không tạo map; key và value không được null |
| `Map.ofEntries(...)` | Một `Map<K, V>` không thể sửa đổi | Có nhiều hơn 10 cặp hoặc đã có các entry riêng lẻ | Nhận varargs entry; không chấp nhận entry null, key/value null hoặc khóa trùng |

Ba phương thức này đều có từ Java 9. Chúng thuộc `java.util.Map`, vì vậy không cần import một lớp triển khai riêng như `HashMap` để gọi factory.

## 5. Các quy tắc quan trọng khi tạo map

### Key phải khác nhau

Map không thể chứa hai ánh xạ có key bằng nhau theo `equals`. Nếu `Map.of` hoặc `Map.ofEntries` nhận các key trùng nhau, lời gọi sẽ ném `IllegalArgumentException` ngay lúc tạo map.

```java
// Ném IllegalArgumentException vì hai key String đều bằng "mode".
Map<String, Integer> invalid = Map.of(
    "mode", 1,
    "mode", 2
);
```

Quy tắc này áp dụng cho cả hai factory tạo map. Với key tự định nghĩa, kết quả so sánh phụ thuộc vào cách lớp đó cài đặt `equals` và `hashCode`; các key được xem là bằng nhau không thể cùng xuất hiện trong map được tạo.

### Không chấp nhận `null`

`Map.of` và `Map.ofEntries` không cho phép key hoặc value là `null`. `Map.entry` cũng không cho phép null ở cả hai vị trí. Các trường hợp này ném `NullPointerException`.

Điều này khác với một số map triển khai như `HashMap`, vốn cho phép một key null và nhiều value null. Nếu dữ liệu đầu vào có thể null, hãy kiểm tra và xử lý trước khi gọi factory.

### Map không thể thay đổi cấu trúc

Các map được tạo bằng `Map.of` và `Map.ofEntries` không hỗ trợ thao tác thay đổi ánh xạ. Những lời gọi như `put`, `remove`, `clear` hoặc `replace` sẽ ném `UnsupportedOperationException`.

```java
Map<String, Integer> codes = Map.of("OK", 200);
codes.put("CREATED", 201); // Ném UnsupportedOperationException
```

Không thể dùng `Map.entry` để thay đổi cặp đã tạo bằng `setValue`.

### Không dựa vào thứ tự duyệt

API không cam kết thứ tự lặp qua `keySet()`, `values()` hoặc `entrySet()` của các map factory này. Thứ tự hiển thị trong lời gọi `Map.of` hay `Map.ofEntries` không phải cam kết thứ tự duyệt.

Nếu chương trình cần thứ tự chèn, hãy dùng `LinkedHashMap`. Nếu cần thứ tự sắp xếp theo key, cân nhắc `TreeMap`. Hai lựa chọn đó có quy tắc thứ tự riêng và có thể được cập nhật theo nhu cầu.

### Unmodifiable không có nghĩa là deep immutable

Map không cho thay đổi các ánh xạ, nhưng value được giữ bên trong không tự động được sao chép hoặc làm bất biến. Ví dụ, nếu value là một `List`, chương trình vẫn có thể sửa danh sách đó thông qua tham chiếu đến danh sách.

Vì vậy, khi cần trạng thái bất biến thực sự, hãy cân nhắc dùng cả key và value bất biến hoặc tạo bản sao bất biến phù hợp cho các object lồng bên trong.

### Không dựa vào identity của map factory

Các map được tạo bằng những factory này là value-based instances. Không nên dùng `==`, `System.identityHashCode`, hoặc khóa đồng bộ `synchronized (map)` để dựa vào danh tính object của chúng. Hãy dùng `equals` để so sánh nội dung map và dùng một object khóa riêng nếu cần đồng bộ.

## 6. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Ví dụ sử dụng cả ba API, đọc dữ liệu từ map, và minh họa các trường hợp không hợp lệ:

```java
import java.util.Map;

public class Main {
    public static void main(String[] args) {
        Map<String, Integer> priorities = Map.of(
            "critical", 1,
            "normal", 2
        );

        Map.Entry<String, Integer> archived = Map.entry("archived", 3);
        Map<String, Integer> states = Map.ofEntries(
            Map.entry("draft", 0),
            archived,
            Map.entry("published", 4)
        );

        System.out.println(priorities.get("normal"));
        System.out.println(states.get("archived"));
        System.out.println(states.size());

        try {
            states.put("new", 5);
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }

        try {
            Map.of("duplicate", 1, "duplicate", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate rejected");
        }

        try {
            Map.entry("null-value", null);
        } catch (NullPointerException ex) {
            System.out.println("null rejected");
        }
    }
}
```

Lưu mã vào `Main.java`, sau đó biên dịch và chạy:

```bash
javac --release 9 Main.java
java Main
```

Kết quả chính xác:

```text
2
3
3
unmodifiable
duplicate rejected
null rejected
```

Ví dụ không duyệt qua `entrySet()` để in toàn bộ map, vì thứ tự duyệt không được API bảo đảm. Thay vào đó, chương trình truy cập bằng key cụ thể để kết quả luôn xác định.

## 7. Khi nào nên dùng factory và khi nào nên dùng map có thể sửa đổi?

Dùng `Map.of` khi tập ánh xạ nhỏ, cố định và có tối đa 10 cặp. Dùng `Map.ofEntries` khi cần tạo map từ nhiều entry hoặc có hơn 10 cặp. Dùng `Map.entry` khi cần biểu diễn một cặp không thể sửa đổi để truyền cho `Map.ofEntries`.

Nếu cần thêm, xóa hoặc cập nhật ánh xạ trong quá trình chạy, hãy tạo một map có thể sửa đổi, chẳng hạn:

```java
Map<String, Integer> counters = new java.util.HashMap<>();
counters.put("success", 0);
counters.put("failure", 0);
counters.merge("success", 1, Integer::sum);
```

Không cần tạo `HashMap` chỉ để chứa vài giá trị cố định rồi không thay đổi nữa; trường hợp đó các factory của `Map` thường diễn đạt ý định rõ hơn.

## 8. Lỗi thường gặp

- Truyền 11 cặp trực tiếp vào `Map.of`: không có overload tương ứng; hãy chuyển sang `Map.ofEntries` và tạo từng cặp bằng `Map.entry`.
- Nghĩ `Map.entry` tự tạo ra một map: phương thức này chỉ trả về một `Map.Entry`.
- Truyền key hoặc value null: factory ném `NullPointerException`; hãy xác thực dữ liệu trước.
- Truyền key trùng: `Map.of` và `Map.ofEntries` ném `IllegalArgumentException`; kiểm tra tính duy nhất của key trước khi tạo.
- Gọi `put` hoặc `remove` trên map factory: thao tác ném `UnsupportedOperationException`; dùng `HashMap` hoặc một triển khai mutable khác nếu cần cập nhật.
- Dựa vào thứ tự in hoặc duyệt map: API không bảo đảm thứ tự; dùng `LinkedHashMap` hoặc `TreeMap` khi thứ tự là yêu cầu.
- Cho rằng value bên trong cũng bất biến: map chỉ ngăn thay đổi ánh xạ; object value có thể vẫn mutable.
- So sánh map factory bằng `==`: hãy so sánh nội dung bằng `equals`, không dựa vào identity của instance.

## 9. Ghi nhớ

1. `Map.of` tạo map từ 0 đến 10 cặp key–value.
2. `Map.entry` tạo một entry không thể sửa đổi, không phải một map.
3. `Map.ofEntries` tạo map từ số lượng entry biến đổi và phù hợp khi có hơn 10 cặp.
4. Cả ba API đều có từ Java 9; key và value không được null.
5. Map factory không chấp nhận key trùng và trả về map không thể sửa đổi.
6. Không dựa vào thứ tự duyệt hoặc identity của map factory; nếu cần map mutable hay có thứ tự, hãy chọn triển khai phù hợp.