# Collection.removeIf(), List.replaceAll() và Collection.forEach() trong Java

Ba API này cho phép truyền **hành vi** vào collection bằng lambda hoặc method reference: lọc bỏ phần tử theo điều kiện, biến đổi từng phần tử và thực hiện một hành động trên từng phần tử. Chúng thường giúp mã ngắn hơn vòng lặp thủ công, nhưng khác nhau về **kiểu callback, khả năng thay đổi dữ liệu và giá trị trả về**.

## 1. Ba API giải quyết ba nhu cầu khác nhau

| API | Nơi khai báo và kiểu callback | Tác động lên collection | Kết quả |
| --- | --- | --- | --- |
| `Collection.removeIf(Predicate<? super E> filter)` | `Collection`; kiểm tra mỗi phần tử, trả `boolean` | Xóa tại chỗ mọi phần tử thỏa điều kiện; có thể giảm kích thước | `boolean`: `true` nếu có phần tử bị xóa |
| `List.replaceAll(UnaryOperator<E> operator)` | `List`; nhận `E`, trả một `E` thay thế | Gán lại từng vị trí trong list; kích thước giữ nguyên | `void` |
| `forEach(Consumer<? super T> action)` | Khai báo ở `Iterable`, `Collection` kế thừa | Gọi hành động cho từng phần tử; bản thân thao tác duyệt không có mục tiêu sửa collection | `void` |

Cả ba được cung cấp từ Java 8. `removeIf` áp dụng cho các collection hỗ trợ xóa, kể cả nhiều `Set`; `replaceAll` chỉ có trên `List`. `forEach` có thể gọi trên mọi `Iterable`, gồm `List`, `Set` và các collection khác.

Cách đọc kiểu callback:
- `Predicate<E>`: `E -> boolean`, dùng để **chọn phần tử cần xóa**.
- `UnaryOperator<E>`: `E -> E`, dùng để **tính giá trị thay thế** cùng kiểu.
- `Consumer<E>`: `E -> void`, dùng để **thực hiện hành động**, chẳng hạn in hoặc ghi log.

## 2. `Collection.removeIf()`: xóa theo điều kiện

Ví dụ muốn loại tất cả số chẵn khỏi danh sách:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4, 5));
boolean changed = numbers.removeIf(n -> n % 2 == 0);
// changed == true; numbers == [1, 3, 5]
```

Đây là đoạn minh họa cần đặt trong phương thức hoặc lớp có import `java.util.ArrayList` và `java.util.List`.

- Java lần lượt kiểm tra các phần tử bằng predicate. Phần tử mà predicate trả `true` là **phần tử bị loại**, không phải phần tử giữ lại.
- Phương thức thay đổi chính collection nhận lệnh; không trả về một collection mới. Khi không xóa phần tử nào, kết quả là `false`.
- Cách cài đặt mặc định dùng `Iterator` và `Iterator.remove()` để xóa phần tử khớp; lớp cụ thể có thể tối ưu hóa cơ chế này, như `ArrayList`.
- Collection không hỗ trợ xóa có thể ném `UnsupportedOperationException`. Chẳng hạn `List.of(...)` là list bất biến; `Arrays.asList(...)` có kích thước cố định và không hỗ trợ xóa phần tử.
- Predicate nên không có tác dụng phụ, đặc biệt không tự thêm/xóa các phần tử của cùng collection trong lúc duyệt.

Khi muốn **giữ nguyên collection gốc** và tạo kết quả mới, dùng `stream().filter(...)` thay cho `removeIf`. Hai cách không tương đương: `removeIf(p)` **xóa** phần tử thỏa `p`, còn `filter(p)` **giữ** phần tử thỏa `p`.

## 3. `List.replaceAll()`: thay từng phần tử tại chỗ

`replaceAll` gọi operator với từng phần tử và ghi kết quả vào vị trí tương ứng:

```java
List<String> words = new ArrayList<>(List.of(" java ", " lambda "));
words.replaceAll(String::trim);
words.replaceAll(String::toUpperCase);
// words == [JAVA, LAMBDA]
```

Đây là đoạn minh họa dùng các import `java.util.ArrayList`, `java.util.List`.

- List vẫn có **cùng số phần tử và cùng vị trí**; giá trị ở các vị trí có thể đổi.
- Operator cần trả về giá trị thay thế. Một lambda dạng `s -> s.trim()` hợp lệ; lambda chỉ gọi `System.out.println(s)` không phù hợp vì không trả về `String`.
- Cách cài đặt mặc định duyệt qua `ListIterator` và dùng `set(...)`. Một list hỗ trợ `set` nhưng không cho thêm/xóa vẫn có thể dùng `replaceAll`; ví dụ `Arrays.asList(...)`.
- List bất biến hoặc không hỗ trợ thay phần tử có thể ném `UnsupportedOperationException`. Trên list cho phép giá trị `null`, operator có thể tạo `null`; hãy bảo đảm kết quả phù hợp quy tắc của list.
- Khi cần **tạo list mới** thay vì sửa tại chỗ, dùng `stream().map(...).toList()` (Java 16+); list trả về từ `Stream.toList()` là không thể sửa.

Đừng nhầm `List.replaceAll(UnaryOperator)` với `Collections.replaceAll(List, oldValue, newValue)`: API thứ hai thay các phần tử **bằng một giá trị cụ thể**, không nhận hàm biến đổi tổng quát.

## 4. `forEach()`: thực thi hành động cho từng phần tử

```java
List<String> names = List.of("An", "Bình", "Chi");
names.forEach(name -> System.out.println("Xin chào " + name));
// Tương đương: names.forEach(System.out::println) khi chỉ muốn in tên.
```

Đây là đoạn minh họa dùng `java.util.List`. Với list có thứ tự như trên, các lời chào xuất hiện theo thứ tự `An`, `Bình`, `Chi`.

- Callback là `Consumer`, không có giá trị trả về. `forEach` thích hợp cho in, gửi kết quả hoặc thao tác phụ được kiểm soát; dùng `map` khi mục tiêu là tính dữ liệu mới.
- Phương thức `forEach` mặc định của `Iterable` thực hiện các hành động theo thứ tự duyệt của iterable, **nếu iterable định nghĩa thứ tự**. Với `HashSet`, không dựa vào thứ tự in cố định.
- `Collection.forEach` được gọi qua kế thừa từ `Iterable`; nó **không phải** `Stream.forEach`. Stream song song có thể xử lý phần tử không theo thứ tự quan sát được; `forEachOrdered` chỉ dành cho stream khi cần giữ encounter order.
- Đừng xóa/thêm phần tử vào chính collection từ bên trong callback. Với nhiều collection, cách làm này có thể dẫn tới `ConcurrentModificationException` hoặc hành vi không đáng tin cậy. Muốn loại phần tử, hãy dùng `removeIf`.

## 5. Ví dụ Java 17+ chạy đầy đủ: phối hợp ba API

Lưu thành tệp `CollectionBehaviorDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class CollectionBehaviorDemo {
    public static void main(String[] args) {
        List<String> labels = new ArrayList<>(
                List.of(" an ", "  ", "Bình", "Chi", "An")
        );

        // Bỏ phần tử chỉ chứa khoảng trắng.
        boolean removed = labels.removeIf(String::isBlank);

        // Chuẩn hóa từng giá trị ở đúng vị trí hiện tại.
        labels.replaceAll(String::trim);
        labels.replaceAll(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("removed = " + removed);
        labels.forEach(s -> System.out.println("item = " + s));
        System.out.println("result = " + labels);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CollectionBehaviorDemo.java
java CollectionBehaviorDemo
```

Kết quả chuẩn:

```text
removed = true
item = AN
item = BÌNH
item = CHI
item = AN
result = [AN, BÌNH, CHI, AN]
```

Diễn giải từng bước:

1. Ban đầu có năm phần tử, gồm chuỗi `"  "` chỉ chứa dấu cách. `String::isBlank` trả `true` cho chuỗi này nên `removeIf` loại nó; `removed` là `true`.
2. `replaceAll(String::trim)` xóa khoảng trắng ở đầu/cuối từng chuỗi còn lại.
3. `replaceAll(s -> s.toUpperCase(Locale.ROOT))` chuyển các chuỗi sang chữ hoa với locale trung lập. Cả hai lời gọi `replaceAll` đều giữ bốn vị trí hiện có.
4. `forEach` in bốn chuỗi đã chuẩn hóa theo thứ tự của `ArrayList`. Dòng cuối xác nhận list gốc đã bị thay đổi ngay tại chỗ.

Cố ý dùng `new ArrayList<>(List.of(...))`: `List.of` cung cấp dữ liệu đầu vào tiện lợi nhưng là list bất biến; `ArrayList` có thể xóa và gán lại phần tử.

## 6. Chọn đúng API theo tình huống

| Yêu cầu | Nên dùng | Lý do |
| --- | --- | --- |
| Loại bản ghi không hợp lệ khỏi một collection có thể sửa | `removeIf(x -> invalid(x))` | Cập nhật collection gốc; trả biết có xóa hay không |
| Chuẩn hóa toàn bộ chuỗi trong list có thể sửa | `replaceAll(String::trim)` | Thay giá trị cùng vị trí, giữ kích thước |
| In, ghi log hoặc phát sinh hành động theo từng phần tử | `forEach(System.out::println)` | Callback kiểu `Consumer` |
| Tạo collection kết quả riêng, giữ dữ liệu gốc | `stream().filter(...).toList()` hoặc `stream().map(...).toList()` | Pipeline tạo kết quả mới, không sửa dữ liệu đầu vào qua thao tác lọc/ánh xạ |

Ví dụ với list có kích thước cố định:

```java
List<String> fixed = java.util.Arrays.asList(" a ", " b ");
fixed.replaceAll(String::trim);             // Hợp lệ: thay các phần tử.
fixed.removeIf(s -> s.equals("a"));          // Ném UnsupportedOperationException.
```

Đây là đoạn minh họa độc lập về khả năng hỗ trợ thao tác, không thuộc chương trình chính. `Arrays.asList` cho phép `set` nhưng không cho xóa phần tử làm thay đổi kích thước. `List.of("a", "b")` không phù hợp cho `replaceAll` hay `removeIf` vì bất biến.

## 7. Lỗi thường gặp và các lưu ý quan trọng

1. **Nhầm logic lọc:** `removeIf(x -> x.isEmpty())` loại chuỗi rỗng. Nếu muốn *giữ* chuỗi rỗng, phải đảo điều kiện.
2. **Nhầm sửa tại chỗ với trả kết quả:** `removeIf` trả `boolean`, còn `replaceAll` và `forEach` trả `void`. Không thể gán kết quả `replaceAll` cho một `List`.
3. **Dùng collection bất biến:** `List.of`, `List.copyOf` và list trả về từ `Stream.toList()` không hỗ trợ các cập nhật cấu trúc/giá trị trên. Sao chép vào `ArrayList` khi cần sửa.
4. **Thay đổi collection ngay trong `forEach`/predicate:** tránh gọi `list.remove(...)` hoặc `list.add(...)` trong callback duyệt chính list đó; sử dụng `removeIf` hoặc thiết kế một lượt xử lý mới.
5. **Giả định thứ tự trên mọi loại collection:** `ArrayList` duyệt theo thứ tự chỉ số, nhưng `HashSet` không hứa hẹn thứ tự nhất định.
6. **Nghĩ callback luôn hoàn tất tất cả phần tử:** nếu predicate/operator/action ném exception, lời gọi có thể dừng giữa chừng; các cập nhật trước đó có thể đã xảy ra. Ba phương thức này không cam kết tính nguyên tử hay tự rollback.
7. **Dùng chung collection giữa nhiều luồng mà không phối hợp:** các API này không tự đồng bộ hóa; phải theo hợp đồng thread-safety của implementation, hoặc chọn cấu trúc/cách đồng bộ thích hợp.
8. **Tác dụng phụ không chủ đích:** nên để predicate và unary operator dễ dự đoán, không phụ thuộc trạng thái thay đổi bên ngoài. Với `forEach`, kiểm soát rõ hành động phụ và xử lý exception nếu cần.

Về chi phí, mỗi API thường cần duyệt qua các phần tử, nhưng độ phức tạp thực tế phụ thuộc implementation và công việc bên trong callback; không nên mặc định mọi `Collection` đều có cùng đặc tính hiệu năng.

## Ghi nhớ

- **`removeIf` = xóa phần tử thỏa `Predicate`**, có thể đổi kích thước và trả `boolean`.
- **`replaceAll` = biến đổi từng giá trị bằng `UnaryOperator`**, giữ kích thước list.
- **`forEach` = thực hiện `Consumer` trên từng phần tử**, không tự tạo list kết quả.

Trước khi dùng các API thay đổi dữ liệu, luôn kiểm tra collection có hỗ trợ **remove** hoặc **set** hay không; đây là ranh giới quan trọng giữa `ArrayList`, list kích thước cố định và list bất biến.
