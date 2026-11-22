# Kiểu phần tử trong for-each trên mảng và Iterable với `var` (Java 10+)

Trong Java, vòng lặp **enhanced `for`** (thường gọi là **for-each**) duyệt lần lượt các phần tử của một **mảng** hoặc một đối tượng có kiểu hỗ trợ **`Iterable`**. Từ Java 10, ta có thể viết `for (var element : source)` để trình biên dịch **suy luận kiểu tĩnh của `element` từ kiểu của `source`**. Quy tắc này tiếp tục được duy trì trong Java hiện đại.

Điểm cốt lõi của bài: **mảng cung cấp kiểu thành phần; `Iterable<T>` cung cấp kiểu phần tử `T`**. `var` không có nghĩa là `Object` trong mọi trường hợp, không làm mất generic khi nguồn có kiểu đầy đủ, và không suy luận kiểu dựa trên đối tượng cụ thể trong từng lượt chạy.

## 1. Cú pháp và điều kiện của for-each

~~~java
for (var element : source) {
    // Dùng element với kiểu được suy luận từ source.
}
~~~

`source` phải là **biểu thức có kiểu mảng** hoặc **kiểu con của `Iterable`**. Java xác định kiểu `element` khi biên dịch, trước khi vòng lặp thực sự chạy.

So sánh với cú pháp ghi kiểu tường minh:

~~~java
int[] numbers = {2, 4, 6};

for (int number : numbers) {
    System.out.println(number);
}

for (var number : numbers) { // Tương đương về kiểu của number: int
    System.out.println(number);
}
~~~

Mỗi đoạn vòng lặp đều in ba dòng `2`, `4`, `6`. `var` ở đây tiết kiệm phần khai báo kiểu `int`; nó **không** đổi thứ tự duyệt, số lượt lặp hoặc kiểu của giá trị.

Trong phần đầu vòng `for-each`, biến lặp **không viết biểu thức khởi tạo**: cú pháp đúng là `for (var number : numbers)`, không phải `for (var number = 0 : numbers)`. Đây là quy tắc riêng của enhanced for, khác với `var number = 0;` khi khai báo biến cục bộ thông thường. Mỗi header for-each khai báo **một biến**.

## 2. Với mảng: `var` suy luận kiểu thành phần

Nếu `source` có kiểu `T[]` thì biến lặp khai báo bằng `var` có kiểu `T`. `T` có thể là kiểu nguyên thủy, kiểu tham chiếu hoặc một kiểu mảng khác.

| Kiểu nguồn | Biến lặp trong `for (var x : source)` | Ghi chú |
| --- | --- | --- |
| `int[]` | `int` | Không tự biến thành `Integer` |
| `long[]` | `long` | Giữ nguyên kiểu nguyên thủy |
| `double[]` | `double` | Hỗ trợ các phép toán `double` |
| `boolean[]` | `boolean` | Giá trị logic nguyên thủy |
| `String[]` | `String` | Gọi được API của `String` |
| `Integer[]` | `Integer` | Kiểu đối tượng bao, phần tử có thể `null` |
| `String[][]` | `String[]` | Mỗi lượt nhận một mảng con |
| `Object[]` | `Object` | Không tự đổi thành kiểu runtime của từng phần tử |

Ví dụ mảng nguyên thủy:

~~~java
int[] scores = {10, 20, 30};
var total = 0;

for (var score : scores) { // score có kiểu int
    total += score;
}

System.out.println(total); // 60
~~~

Ví dụ mảng tham chiếu:

~~~java
String[] names = {"An", "Binh"};

for (var name : names) { // name có kiểu String
    System.out.println(name.length());
}
~~~

Mảng `String[]` khai báo kiểu `String` cho mọi phần tử, nên `name.length()` hợp lệ. Nếu nguồn là `Object[]` chứa các chuỗi, `var name` vẫn có kiểu `Object`: lời gọi `name.length()` sẽ không biên dịch vì `Object` không có `length()`.

### Mảng nhiều chiều: suy luận giảm một mức chiều

~~~java
String[][] groups = {{"An", "Binh"}, {"Mai"}};

for (var group : groups) { // group có kiểu String[]
    System.out.println(group.length);
}
~~~

Kết quả:

~~~text
2
1
~~~

`group.length` là **số phần tử của mảng con**, không phải độ dài của một chuỗi. Muốn duyệt từng chuỗi:

~~~java
for (var group : groups) {         // String[]
    for (var name : group) {        // String
        System.out.println(name);
    }
}
~~~

Bất kỳ số chiều nào cũng tuân theo cùng nguyên tắc: `int[][][]` sẽ cho biến lặp ngoài cùng có kiểu `int[][]`.

## 3. Với `Iterable<T>`: `var` suy luận từ tham số kiểu `T`

`Iterable<T>` là giao diện mô tả khả năng cung cấp một `Iterator<T>` thông qua phương thức `iterator()`. Nhiều cấu trúc phổ biến như `List<String>`, `Set<Integer>` triển khai `Iterable<T>`.

~~~java
java.util.List<String> labels = java.util.List.of("Java", "10");

for (var label : labels) { // label có kiểu String
    System.out.println(label.toLowerCase(java.util.Locale.ROOT));
}
~~~

Kết quả:

~~~text
java
10
~~~

Dù lớp đối tượng của `labels` có thể là một triển khai nội bộ của `List`, kiểu phần tử vẫn xuất phát từ **kiểu của biểu thức nguồn tại điểm biên dịch**: `List<String>` là một `Iterable<String>`, vì vậy `label` là `String`.

Khi sử dụng một biến kiểu `Iterable<T>` trực tiếp, quy tắc cũng không đổi:

~~~java
Iterable<String> tags = java.util.List.of("spring", "java");

for (var tag : tags) {   // String, không phải Object
    System.out.println(tag.toUpperCase(java.util.Locale.ROOT));
}
~~~

Mã sử dụng `Iterable<String>` vẫn giữ thông tin generic `String`. Lựa chọn khai báo `Iterable<T>` có thể hữu ích khi mã chỉ cần khả năng duyệt phần tử và không cần các phương thức riêng như `List.get(int)`.

### Triển khai `Iterable` tùy chỉnh

Một lớp không cần kế thừa `List` mới dùng được với for-each: chỉ cần triển khai `Iterable<T>` phù hợp.

~~~java
Iterable<String> codes =
        () -> java.util.List.of("A", "B").iterator();

for (var code : codes) { // String
    System.out.println(code);
}
~~~

Đây là **đoạn minh họa đặt trong phương thức**. Lambda hợp lệ vì `Iterable<String>` có một phương thức trừu tượng `iterator()`. Cách dùng `var code` không phụ thuộc vào việc `codes` được tạo qua lambda, lớp tự viết hay `List`; nó phụ thuộc vào hợp đồng `Iterable<String>`.

## 4. Generics quyết định khả năng dùng API của phần tử

Khi vòng lặp dùng `var` trên `Iterable<T>`, nó **không xóa thông tin kiểu generic**.

~~~java
Iterable<String> names = java.util.List.of("An", "Mai");

for (var name : names) { // String
    System.out.println(name.length()); // Đúng: String có length()
}
~~~

Đổi nguồn thành `Iterable<Integer>`, `name` tương ứng có kiểu `Integer`, không phải `String`:

~~~java
Iterable<Integer> ages = java.util.List.of(18, 20);

for (var age : ages) { // Integer
    System.out.println(age.intValue());
    // age.length();    // Lỗi biên dịch: Integer không có length()
}
~~~

`Iterable<Integer>` cũng khác `int[]`: trong `for (var age : ages)`, `age` có kiểu tham chiếu `Integer`, còn trong `for (var age : intArray)`, `age` có kiểu nguyên thủy `int`. Java có thể **tự unbox** `Integer` thành `int` khi thực hiện phép toán phù hợp, nhưng việc đó không khiến kiểu được suy luận ban đầu trở thành `int`.

### Khi phần tử có thể `null`

~~~java
java.util.List<Integer> maybeNull =
        java.util.Arrays.asList(1, null, 3);

for (var value : maybeNull) { // Integer, có thể là null
    if (value != null) {
        System.out.println(value + 1); // Unboxing khi cộng
    }
}
~~~

Nếu bỏ kiểm tra `null` rồi dùng `value + 1` khi `value` là `null`, sẽ phát sinh `NullPointerException` do unboxing. Đây là tính chất của `Integer` và dữ liệu, không phải lỗi của `var`.

## 5. Wildcard: đọc được gì từ `? extends` và `? super`?

Các ràng buộc generic vẫn áp dụng khi dùng `var` trong for-each.

### Nguồn `Iterable<? extends Number>`

~~~java
Iterable<? extends Number> values =
        java.util.List.of(2, 3.5);

for (var value : values) {
    System.out.println(value.doubleValue());
}
~~~

Kết quả:

~~~text
2.0
3.5
~~~

Kiểu phần tử được suy luận theo tham số wildcard với **giới hạn trên `Number`**. Ta có thể dùng các phương thức được bảo đảm trên `Number`, như `doubleValue()`, nhưng **không thể giả định mọi phần tử đều là `Integer`**: trong ví dụ có cả `Integer` và `Double`.

Theo đặc tả, kiểu suy luận còn được xử lý qua cơ chế *upward projection* đối với biến kiểu nội bộ do capture wildcard. Với ví dụ thực tế này, điều quan trọng là: **mã xử lý phần tử an toàn theo hợp đồng `Number`** và không phụ thuộc vào lớp con cụ thể.

### Nguồn `Iterable<? super Integer>`

~~~java
Iterable<? super Integer> values =
        java.util.List.<Number>of(3, 4);

for (var value : values) {
    Object object = value; // Luôn hợp lệ
    System.out.println(object);
}
~~~

Kết quả:

~~~text
3
4
~~~

Với giới hạn dưới `? super Integer`, kiểu nguồn có thể là `Iterable<Integer>`, `Iterable<Number>` hoặc `Iterable<Object>`. Khi **đọc** phần tử, ta không được mặc định đó là `Integer`: mức an toàn chung là `Object`. Không thể gọi `value.intValue()` trực tiếp như thể biến chắc chắn là `Integer`.

Với `Iterable<?>`, phần tử cũng không có một kiểu cụ thể hơn được bảo đảm để gọi API riêng; cách đọc an toàn chung là qua `Object`.

Các wildcard không làm `var` trở thành “động”. Trình biên dịch vẫn áp dụng giới hạn kiểu tại thời điểm biên dịch.

## 6. Phương thức generic và biến kiểu `T`

Trong mã generic, nếu nguồn có kiểu `Iterable<T>`, biến lặp cũng được suy luận theo `T` (cùng các ràng buộc kiểu của `T`):

~~~java
static <T> void printItems(Iterable<T> items) {
    for (var item : items) { // Kiểu T
        System.out.println(item);
    }
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp. Với `T` không bị ràng buộc, bạn không thể mặc nhiên gọi `item.length()` hoặc `item.intValue()`. Nếu cần tính chất của `Number`, hãy dùng giới hạn kiểu:

~~~java
static <T extends Number> double sumValues(Iterable<T> values) {
    double sum = 0;
    for (var value : values) { // T extends Number
        sum += value.doubleValue();
    }
    return sum;
}
~~~

Kiểu `T` được bảo toàn trong phần thân phương thức; `var` không xóa ràng buộc `extends Number`.

## 7. Chương trình đầy đủ, có thể chạy

Lưu nội dung sau vào **`VarForEachTypesDemo.java`**:

~~~java
import java.util.List;

public class VarForEachTypesDemo {
    public static void main(String[] args) {
        int[] scores = {2, 4, 6};
        int sum = 0;

        for (var score : scores) { // int
            sum += score;
        }
        System.out.println("sum=" + sum);

        String[][] groups = {{"An", "Binh"}, {"Mai"}};
        for (var group : groups) { // String[]
            System.out.println("group=" + group.length);
        }

        Iterable<String> tags = List.of("Java", "10");
        for (var tag : tags) { // String
            System.out.println("tag=" + tag);
        }

        Iterable<? extends Number> stats = List.of(2, 3.5);
        for (var stat : stats) {
            System.out.println("num=" + stat.doubleValue());
        }

        Iterable<? super Integer> general = List.<Number>of(3, 4);
        for (var element : general) {
            Object object = element;
            System.out.println("super=" + object);
        }

        // Một Iterable do lập trình viên tạo.
        Iterable<String> generated =
                () -> List.of("X", "Y").iterator();
        for (var code : generated) { // String
            System.out.println("generated=" + code);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**; các tính năng trong chương trình tương thích từ **Java 10**:

~~~bash
javac VarForEachTypesDemo.java
java VarForEachTypesDemo
~~~

`stdout`:

~~~text
sum=12
group=2
group=1
tag=Java
tag=10
num=2.0
num=3.5
super=3
super=4
generated=X
generated=Y
~~~

Giải thích: vòng lặp mảng `int[]` cộng các `int`; mảng `String[][]` được duyệt thành từng `String[]`; nguồn `Iterable<String>` cho kiểu `String`; wildcard giới hạn trên cho phép gọi `Number.doubleValue()`; wildcard giới hạn dưới chỉ bảo đảm đọc được như `Object`. `Iterable<String>` tự tạo cũng hoạt động như nguồn danh sách vì cung cấp `Iterator<String>`.

## 8. Những giới hạn và lỗi thường gặp

### Không phải đối tượng nào cũng dùng trực tiếp được với for-each

~~~java
var names = java.util.List.of("An", "Mai"); // Iterable<String>
for (var name : names) {
    System.out.println(name);
}
~~~

Nhưng `Map<K, V>` **không** tự nó là `Iterable`. Để duyệt từng cặp khóa/giá trị:

~~~java
var counts = java.util.Map.of("An", 2, "Mai", 3);

for (var entry : counts.entrySet()) { // Map.Entry<String, Integer>
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

Tương tự, `Stream<T>` không tự nó là `Iterable<T>`, nên không thể viết trực tiếp `for (var x : stream)`. Với một `Stream` hữu hạn và có nhu cầu duyệt bằng for-each, có thể chuyển thành `List` bằng `stream.toList()` (Java 16+) rồi duyệt danh sách; hoặc dùng các thao tác xử lý stream phù hợp với bài toán. Ví dụ:

~~~java
var stream = java.util.stream.Stream.of("An", "Mai");
for (var name : stream.toList()) { // Java 16+
    System.out.println(name);
}
~~~

Mảng là trường hợp riêng được ngôn ngữ hỗ trợ trực tiếp trong for-each; bản thân mảng Java **không triển khai `Iterable`**.

### Không đoán kiểu từ nội dung runtime

~~~java
Object[] values = {"An", "Mai"};
for (var value : values) { // Object, dù phần tử thực tế là String
    System.out.println(value);
    // value.length();      // Không biên dịch
}
~~~

Giải pháp là khai báo nguồn có kiểu phù hợp (`String[]`, `Iterable<String>`, v.v.) nếu hợp đồng dữ liệu cho phép, hoặc kiểm tra kiểu rõ ràng khi phải xử lý dữ liệu hỗn hợp.

### `var` trong for-each không khởi tạo bằng dấu bằng

Các ví dụ sau **không hợp lệ**, không đưa vào chương trình chạy:

~~~java
// for (var x = 0 : scores) { }   // Sai: header for-each không có = 0
// for (var x, y : scores) { }    // Sai: nhiều biến trong một khai báo
// for (var x : 42) { }           // Sai: int không phải mảng/Iterable
~~~

`var` cũng không thay đổi quy tắc phạm vi: biến lặp chỉ tồn tại bên trong phần thân vòng lặp. Nếu muốn giữ giá trị sau vòng lặp, hãy khai báo biến kết quả bên ngoài, như `sum` trong chương trình đầy đủ.

### Gán lại biến lặp không sửa phần tử nguồn

~~~java
int[] values = {1, 2};

for (var value : values) {
    value += 10; // Chỉ thay đổi biến cục bộ value.
}

System.out.println(values[0]); // Vẫn là 1
~~~

Enhanced for nhận giá trị phần tử (đối với kiểu tham chiếu là **giá trị tham chiếu**). Để thay phần tử mảng tại một chỉ số, dùng vòng `for` có chỉ số rồi gán `values[i]`. Với phần tử là đối tượng có trạng thái thay đổi được, có thể gọi phương thức sửa trạng thái đối tượng thông qua tham chiếu; điều đó khác với gán lại biến lặp.

Nếu muốn **cấm gán lại chính biến lặp**, có thể viết `for (final var value : values)`. `final` không làm kiểu `value` thay đổi và không tự khiến đối tượng được tham chiếu trở thành bất biến.

### Nguồn `null` và phần tử `null`

Nếu biểu thức nguồn được đánh giá thành `null`, for-each sẽ không thể lấy phần tử và phát sinh `NullPointerException`. Nếu chính **phần tử** là `null`, biến lặp kiểu tham chiếu có thể nhận `null`, nhưng việc gọi phương thức hoặc tự unbox nó có thể gây lỗi. Kiểm tra dữ liệu theo hợp đồng API thay vì cho rằng `var` tự xử lý `null`.

## 9. Bảng quyết định nhanh

| Biểu thức nguồn | Kiểu biến lặp `var item` | Điều nên kiểm tra |
| --- | --- | --- |
| `new int[] {1, 2}` | `int` | Kiểu nguyên thủy |
| `new String[] {"A"}` | `String` | Phương thức của `String` |
| `new String[][] {{"A"}}` | `String[]` | Duyệt tiếp nếu cần phần tử bên trong |
| `List.of("A", "B")` | `String` | `List<String>` triển khai `Iterable<String>` |
| Biến `Iterable<Integer>` | `Integer` | Boxing/unboxing, khả năng `null` từ nguồn |
| Biến `Iterable<? extends Number>` | Theo giới hạn trên `Number` | Dùng phương thức của `Number` |
| Biến `Iterable<? super Integer>` | Chỉ an toàn chung như `Object` | Không mặc định phần tử là `Integer` |
| Biến `Iterable<T>` trong phương thức generic | `T` | Xét các ràng buộc của `T` |
| Biến `Object[]` chứa chuỗi | `Object` | Kiểu tĩnh của nguồn, không phải lớp runtime |

## 10. Tự kiểm tra

Xác định kiểu tĩnh của từng biến lặp và cho biết lời gọi nào hợp lệ:

~~~java
int[] a = {1, 2};
Integer[] b = {1, 2};
String[][] c = {{"A"}, {"B", "C"}};
Iterable<String> d = java.util.List.of("X", "Y");
Iterable<? extends Number> e = java.util.List.of(1, 2.5);

for (var x : a) {
    System.out.println(x + 1);
}
for (var x : b) {
    System.out.println(x.intValue());
}
for (var x : c) {
    System.out.println(x.length);
}
for (var x : d) {
    System.out.println(x.toLowerCase(java.util.Locale.ROOT));
}
for (var x : e) {
    System.out.println(x.doubleValue());
}
~~~

**Đáp án:** `a` cho `int`; `b` cho `Integer`; `c` cho `String[]`; `d` cho `String`; `e` cho kiểu sử dụng an toàn theo `Number`. Tất cả các lời gọi trong ví dụ đều hợp lệ. Không thể đổi `x.length` trên `String[]` thành `x.length()` vì mảng có trường `length`, còn chuỗi có phương thức `length()`.

## 11. Ghi nhớ và tài liệu

- Với **mảng `T[]`**, `var` trong for-each suy luận kiểu thành phần **`T`**; với mảng nhiều chiều, `T` có thể tiếp tục là mảng.
- Với **`Iterable<T>`**, suy luận kiểu phần tử từ tham số generic **`T`** và các giới hạn liên quan.
- Kiểu suy luận là **kiểu tĩnh**, không thay đổi theo đối tượng trong từng lượt lặp.
- `Integer[]` và `Iterable<Integer>` cho kiểu `Integer`, còn `int[]` cho `int`; chú ý null/unboxing.
- For-each chỉ nhận mảng hoặc nguồn tương thích `Iterable`; `var` không thay đổi quy tắc này.

Tham khảo chính thức: [Java Language Specification, `14.14.2 — The enhanced for statement (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.14.2) và [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286).
