# Dùng `var` trong vòng lặp for-each của Java

## Mục tiêu

Trong Java 10 trở lên, `var` có thể thay kiểu được viết tường minh của **biến phần tử trong vòng lặp enhanced `for`** (thường gọi là *for-each*). Sau bài học, bạn sẽ biết khi nào viết `for (var item : source)`, trình biên dịch xác định kiểu của `item` ra sao, cách dùng với mảng và collection, và những lỗi cần tránh trong code Java hiện đại.

## 1. Cú pháp: `var` thay kiểu của biến phần tử

Cú pháp chuẩn của vòng lặp for-each là:

~~~java
for (var element : arrayOrIterable) {
    // Sử dụng element trong thân vòng lặp.
}
~~~

Trong đó:

- `element` là **biến cục bộ của từng lượt lặp**; phạm vi sử dụng của nó nằm trong thân vòng lặp.
- `arrayOrIterable` phải là biểu thức hợp lệ cho enhanced `for`: một **mảng** hoặc một đối tượng có kiểu thực thi `Iterable` (ví dụ `List`, `Set`).
- Dấu `:` nghĩa là lần lượt lấy phần tử từ nguồn lặp; **không phải** cú pháp gán giá trị.
- `var` yêu cầu Java 10+ và phải đứng ở vị trí khai báo biến phần tử. Viết `for (String element : source)` vẫn hoàn toàn hợp lệ.

So sánh hai cách viết tương đương về kiểu:

~~~java
List<String> names = List.of("An", "Binh");

for (String name : names) {
    System.out.println(name);
}

for (var name : names) {
    System.out.println(name);
}
~~~

Trong cả hai vòng lặp, `name` có **kiểu tĩnh `String`**. Trình biên dịch suy luận kiểu đó từ `List<String>`, nên bạn vẫn được kiểm tra kiểu khi gọi phương thức hoặc thực hiện phép gán. `var` không tạo ra một kiểu dữ liệu động.

**Điểm khác so với khai báo `var` cục bộ thông thường:** `var name = "An";` cần biểu thức bên phải để suy luận kiểu; trong `for (var name : names)`, biến được nhận phần tử ở mỗi lượt lặp nên **không có** dấu `=` hoặc giá trị khởi tạo riêng.

## 2. Kiểu của biến được xác định tại thời điểm biên dịch

Trình biên dịch suy luận kiểu từ **kiểu phần tử của nguồn lặp**, chứ không đợi đến lúc chạy để xem phần tử đang chứa đối tượng gì.

| Nguồn lặp | Ví dụ | Kiểu của biến `var` |
| --- | --- | --- |
| Mảng nguyên thủy | `for (var n : new int[]{1, 2})` | `int` |
| Mảng tham chiếu | `for (var s : new String[]{"a", "b"})` | `String` |
| Collection có generic | `for (var s : List.of("a", "b"))` | `String` |
| `List<Integer>` | `for (var n : List.of(1, 2))` | `Integer` |
| `List<Number>` | `for (var n : numbers)` với `numbers` là `List<Number>` | `Number` |
| `Map<String, Integer>.entrySet()` | `for (var e : map.entrySet())` | `Map.Entry<String, Integer>` |

Hai hệ quả quan trọng:

1. Với mảng `int[]`, `var n` là **`int` nguyên thủy**. Với `List<Integer>`, `var n` là **`Integer` tham chiếu**, vì generic của collection chứa `Integer`; phép toán số học có thể kích hoạt *auto-unboxing*, nhưng không thay đổi kiểu tĩnh của biến.
2. Nếu nguồn lặp được khai báo là `List<Number>` nhưng phần tử thực tế có thể là `Integer` hoặc `Double`, `var element` vẫn có kiểu tĩnh `Number`. Bạn chỉ gọi trực tiếp được những phương thức mà kiểu `Number` cho phép, dù một phần tử cụ thể là lớp con.

Dùng `var` **không tự động biến** một nguồn lặp dùng raw type thành collection có generic an toàn. Hãy khai báo generic rõ ràng cho `List<T>`, `Set<T>` hoặc `Iterable<T>` để kiểu phần tử được suy luận chính xác.

## 3. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây duyệt `List<String>`, mảng `int[]` và các entry của `LinkedHashMap<String, Integer>`. `LinkedHashMap` giữ thứ tự chèn trong ví dụ để kết quả in ra xác định.

Lưu vào file **VarForEachDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;

public class VarForEachDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");

        // name được suy luận là String.
        for (var name : names) {
            System.out.println(name.toUpperCase());
        }

        int[] points = {3, 5, 7};
        var total = 0;

        // point được suy luận là int.
        for (var point : points) {
            total += point;
        }
        System.out.println("Tong = " + total);

        var scores = new LinkedHashMap<String, Integer>();
        scores.put("An", 9);
        scores.put("Binh", 8);

        // entry được suy luận là Map.Entry<String, Integer>.
        for (var entry : scores.entrySet()) {
            System.out.println(entry.getKey() + " -> " + entry.getValue());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac VarForEachDemo.java
java VarForEachDemo
~~~

Kết quả chuẩn:

~~~text
AN
BINH
Tong = 15
An -> 9
Binh -> 8
~~~

**Vì sao mã chạy được?** `names` có kiểu `List<String>`, nên các phần tử `name` là `String` và `toUpperCase()` hợp lệ. `points` là `int[]`, nên mỗi `point` là `int` và cộng được vào `total`. `scores.entrySet()` có kiểu `Set<Map.Entry<String, Integer>>`, cho phép `entry.getKey()` trả về `String` và `entry.getValue()` trả về `Integer` theo khai báo generic.

Chú ý: bạn **không thể** lặp trực tiếp trên `Map` bằng `for (var entry : scores)`, vì `Map` không triển khai `Iterable`. Với `Map`, hãy chọn `entrySet()`, `keySet()` hoặc `values()` tùy mục đích.

## 4. `var` vẫn tuân theo kiểm tra kiểu tĩnh

Đoạn dưới đây là **ví dụ lỗi biên dịch có chủ ý**, không thuộc chương trình hoàn chỉnh ở mục 3:

~~~java
for (var point : new int[]{1, 2, 3}) {
    // point = "ba"; // Lỗi: không thể gán String cho int.
    System.out.println(point + 1);
}

for (var text : List.of("java", "kotlin")) {
    // text = 123; // Lỗi: không thể gán int cho String.
    System.out.println(text.length());
}
~~~

`var` chỉ loại bỏ việc gõ lặp lại tên kiểu, **không loại bỏ kiểm tra kiểu**. Nếu cần làm rõ ý định thiết kế, viết `for (Number number : numbers)` hoặc `for (String name : names)` vẫn là lựa chọn tốt.

Với biến được khai báo `final var`, Java cũng cho phép ràng buộc không gán lại trong thân vòng lặp:

~~~java
for (final var name : List.of("An", "Binh")) {
    System.out.println(name);
    // name = "Khac"; // Lỗi: name là biến final.
}
~~~

Từ khóa `final` ngăn **gán lại biến**, không tự động làm một đối tượng tham chiếu trở nên bất biến.

## 5. Gán lại biến for-each không thay phần tử trong collection

Trong vòng lặp, `var` tạo một **biến cục bộ để nhận lần lượt giá trị/phần tử**. Nếu biến là tham chiếu, nó trỏ đến cùng đối tượng với phần tử lấy từ collection tại thời điểm đó; **gán lại biến** chỉ đổi tham chiếu cục bộ, không thay thế phần tử ở collection.

Đoạn ví dụ sau có thể đặt trong phương thức `main` với import `java.util.ArrayList` và `java.util.List`:

~~~java
var words = new ArrayList<>(List.of("an", "binh"));

for (var word : words) {
    word = word.toUpperCase();
}

System.out.println(words); // [an, binh]

words.replaceAll(String::toUpperCase);
System.out.println(words); // [AN, BINH]
~~~

Vì `String` bất biến, `word.toUpperCase()` trả về một chuỗi mới. Phép `word = ...` không gọi `set` lên `List`, nên danh sách vẫn chứa giá trị ban đầu. Khi muốn biến đổi từng phần tử trong một `List` **có thể sửa**, `replaceAll` là một cách rõ ràng.

Nếu phần tử là đối tượng **có thể thay đổi trạng thái**, lời gọi phương thức trên chính đối tượng ấy có thể làm thay đổi đối tượng đang được collection tham chiếu; điều này khác với việc gán lại biến `word`. Cũng đừng xóa/thêm phần tử vào nhiều collection ngay trong enhanced `for`: tùy collection, cách đó có thể gây `ConcurrentModificationException`. Khi cần lọc phần tử, phương thức như `removeIf` thường phù hợp hơn.

## 6. Phân biệt `var` trong for-each với các cú pháp khác

**Vòng lặp for-each:**

~~~java
for (var name : List.of("An", "Binh")) {
    System.out.println(name);
}
~~~

Mỗi lượt, Java lấy phần tử kế tiếp từ nguồn lặp. Bạn không thao tác trực tiếp với chỉ số trong cú pháp này.

**Vòng lặp for truyền thống:**

~~~java
for (var index = 0; index < 3; index++) {
    System.out.println(index);
}
~~~

Ở đây `index` là `int` được suy luận từ biểu thức khởi tạo `0`; đây là một trường hợp dùng `var` khác với for-each. Hãy chọn `for` truyền thống khi thật sự cần chỉ số, bước nhảy hoặc điều kiện vòng lặp không phụ thuộc vào việc lấy từng phần tử.

**Stream không trực tiếp là Iterable:**

~~~java
// Không hợp lệ: Stream không triển khai Iterable.
// for (var s : java.util.stream.Stream.of("An", "Binh")) { ... }

// Hợp lệ trên Java 17+: chuyển Stream thành List rồi lặp.
for (var s : java.util.stream.Stream.of("An", "Binh").toList()) {
    System.out.println(s);
}
~~~

Cú pháp for-each yêu cầu mảng hoặc `Iterable`; nó không biến một `Stream` hay một `Iterator` thành nguồn enhanced `for` chỉ vì bạn dùng `var`.

## 7. Các lỗi thường gặp

| Viết như sau | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| `for (var e = 0 : items)` | For-each không có khai báo `var` kèm phép gán `=`. | `for (var e : items)` |
| `for (var e : map)` | `Map` không phải `Iterable`. | `for (var e : map.entrySet())` |
| `for (var e : stream)` | `Stream` không phải `Iterable`. | Sử dụng API `Stream` hoặc chuyển sang một collection để duyệt. |
| Gán `e = giaTriMoi` để sửa danh sách | Chỉ gán lại biến cục bộ. | Dùng API sửa collection thích hợp, chẳng hạn `List.replaceAll`. |
| Giả định `var n` trên `List<Integer>` là `int` | Kiểu suy luận là `Integer`. | Nhớ phân biệt generic reference type và primitive array. |
| Dùng raw `Iterable` rồi kỳ vọng `e` là `String` | Raw type làm mất thông tin phần tử; biến thường có kiểu `Object`. | Khai báo `Iterable<String>` hoặc `List<String>`. |

Ngoài ra, nếu collection chứa các tham chiếu `null`, khai báo `var element` vẫn có kiểu tĩnh theo generic của collection. Việc gọi phương thức trên `element` khi nó là `null` vẫn có thể gây `NullPointerException` lúc chạy. `var` không tự thêm cơ chế kiểm tra `null`.

## 8. Khi nào nên dùng?

Dùng `var` trong for-each khi **kiểu phần tử rõ từ tên/khai báo nguồn lặp**, ví dụ `List<String>`, mảng `int[]`, hoặc `map.entrySet()`. Điều này đặc biệt gọn với kiểu dài như `Map.Entry<String, Integer>`.

Ưu tiên viết tên kiểu rõ ràng nếu nguồn lặp có generic phức tạp, kiểu suy luận không hiển nhiên hoặc việc nhìn thấy kiểu là điều quan trọng đối với người bảo trì. Tính dễ hiểu của đoạn mã quan trọng hơn độ ngắn của cú pháp.

`var` không khiến vòng lặp nhanh hơn hay chậm hơn chỉ vì bỏ tên kiểu; quá trình suy luận kiểu diễn ra lúc biên dịch, và cơ chế duyệt mảng hoặc `Iterable` vẫn theo quy tắc Java thông thường.

## 9. Tự kiểm tra

Hãy xác định kiểu của biến lặp và dự đoán kết quả:

~~~java
List<Integer> numbers = List.of(2, 4, 6);
var sum = 0;

for (var n : numbers) {
    sum += n;
}

System.out.println(sum);
~~~

**Đáp án:** `n` có kiểu tĩnh `Integer` do nguồn là `List<Integer>`. Biểu thức `sum += n` sử dụng auto-unboxing để cộng số nguyên. Kết quả in ra là `12`; `sum` vẫn có kiểu `int`. Nếu đổi nguồn thành `int[]`, biến `n` sẽ được suy luận là `int`.

**Ghi nhớ:** Với `for (var element : source)`, trình biên dịch xác định **kiểu phần tử từ mảng hoặc `Iterable` tại thời điểm biên dịch**. Biến lặp vẫn được kiểm tra kiểu tĩnh, chỉ có phạm vi trong vòng lặp, và việc gán lại biến ấy không đồng nghĩa sửa phần tử nguồn.
