# Cú pháp for-each cho mảng và Iterable

## 1. For-each diễn tả việc gì?

Vòng lặp **for-each**, còn gọi là **enhanced for**, diễn tả yêu cầu “lần lượt xử lý từng phần tử của một nguồn dữ liệu”.

Nếu công việc chỉ cần giá trị phần tử, không cần tính toán chỉ số, cú pháp này làm rõ ý định:

```java
int[] scores = {7, 8, 9};

for (int score : scores) {
    System.out.println(score);
}
```

Đây là đoạn mã đặt bên trong một phương thức. Mỗi lượt lặp nhận một giá trị từ `scores`, gán vào biến cục bộ `score` rồi thực hiện thân vòng lặp.

Ba giá trị được in theo thứ tự `7`, `8`, `9`.

Trong Java, nguồn ở bên phải dấu `:` phải là:

- Một **mảng**.
- Hoặc một biểu thức có kiểu phù hợp với **`Iterable`**.

Không phải mọi đối tượng “có nhiều dữ liệu” đều tự động dùng trực tiếp được với for-each. Kiểu tĩnh của biểu thức phải đáp ứng quy tắc của ngôn ngữ.

Cú pháp và điều kiện được định nghĩa trong [JLS: The enhanced for statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2).

## 2. Đọc từng thành phần của cú pháp

Trong:

```java
for (String name : names) {
    System.out.println(name);
}
```

- `String` là kiểu của biến lặp.
- `name` là một biến được khai báo cho các lượt lặp.
- `names` là biểu thức nguồn.
- Dấu `:` tách khai báo biến với nguồn.
- Khối `{ ... }` chứa công việc thực hiện cho mỗi phần tử.

Đoạn này giả định `names` là mảng chuỗi hoặc một `Iterable` có phần tử phù hợp, chẳng hạn `List<String>`.

Khác vòng `for` cơ bản, phần trong ngoặc của for-each không có ba vế khởi tạo, điều kiện và cập nhật chỉ số. Cơ chế duyệt được xác định từ loại nguồn.

### Biến lặp phải được khai báo tại đó

Cách thông thường là `for (String name : names)`, không phải bỏ kiểu rồi dùng một biến cũ ở ngoài:

```java
// String name;
// for (name : names) { } // Khong bien dich
```

Đây là các dòng minh họa cú pháp không hợp lệ, được chú thích để không bị hiểu là chương trình chạy.

Biến lặp có phạm vi trong phần thân vòng lặp. Sau vòng lặp, không sử dụng chính biến đó như một biến kết quả bên ngoài.

Nếu cần tổng, số lượng hoặc một kết quả tìm kiếm, khai báo biến tích lũy riêng ở ngoài vòng lặp.

### Nên dùng khối lệnh rõ ràng

Dù một thân chỉ có một câu lệnh có thể bỏ ngoặc nhọn, giữ `{ }` giúp việc thêm lệnh và đọc phạm vi của biến dễ hơn.

Không đặt dấu `;` ngay sau dấu `)` theo thói quen. Một thân rỗng như `for (int value : values);` có thể hợp lệ về cú pháp nhưng không thực hiện khối xử lý mà người viết tưởng nằm trong vòng lặp.

## 3. Duyệt mảng: phần tử đi theo thứ tự chỉ số

For-each áp dụng cho mảng nguyên thủy lẫn mảng tham chiếu.

### Mảng nguyên thủy

```java
int[] values = {10, 20, 30};
int total = 0;

for (int value : values) {
    total += value;
}
```

Sau vòng lặp, `total` bằng `60`. Giá trị được lấy lần lượt từ vị trí `0` tới `length - 1`.

Ta không viết hoặc cập nhật chỉ số thủ công. Biến `value` nhận giá trị của từng phần tử.

### Mảng tham chiếu

```java
String[] names = {"An", "Binh"};

for (String name : names) {
    System.out.println(name);
}
```

Biến `name` giữ tham chiếu tới phần tử hiện tại. Nó không phải một bản sao sâu của đối tượng chuỗi.

### Mảng nhiều chiều

Với `int[][]`, phần tử của mảng ngoài là một `int[]`:

```java
int[][] matrix = {{1, 2}, {3}};

for (int[] row : matrix) {
    for (int value : row) {
        System.out.println(value);
    }
}
```

Một vòng lặp ngoài không tự động làm phẳng toàn bộ ma trận. Cần vòng lặp trong để đi qua các phần tử của mỗi hàng.

Các hàng có thể có độ dài khác nhau. Nếu một hàng là `null`, vòng lặp trong trên hàng đó sẽ gặp `NullPointerException`; phải chọn chính sách xử lý dữ liệu thiếu riêng.

### Mảng không cần cài đặt Iterable

Mảng dùng được với for-each nhờ quy tắc riêng của ngôn ngữ Java. Điều đó không có nghĩa `int[]` tự trở thành một đối tượng `Iterable<Integer>` hoặc tự có phương thức `iterator()` mà mã nguồn gọi được.

Đây là hai con đường hỗ trợ cú pháp, cùng cho phép viết for-each nhưng không phải cùng một quan hệ kiểu.

## 4. Duyệt Iterable: đi theo bộ lặp của nguồn

`Iterable<T>` là hợp đồng cho một đối tượng có thể cung cấp bộ lặp `Iterator<T>`.

Ví dụ:

```java
Iterable<String> names = List.of("An", "Binh");

for (String name : names) {
    System.out.println(name);
}
```

Đoạn này cần import `java.util.List` khi đặt trong chương trình.

Biến `names` được khai báo ở mức `Iterable<String>` cũng đủ. Không bắt buộc kiểu tĩnh phải là `ArrayList` hoặc `List`.

Cơ chế có thể hiểu là:

1. Lấy đối tượng nguồn.
2. Lấy bộ lặp từ nguồn qua `iterator()`.
3. Khi bộ lặp còn phần tử, lấy phần tử kế tiếp.
4. Gán nó cho biến lặp và thực hiện thân.

Đây là giải thích cơ chế; không cần tự viết các bước đó khi for-each đã mô tả đúng tác vụ.

Các kiểu `List`, `Set` và nhiều kiểu tập hợp khác hỗ trợ `Iterable`. Một lớp tự viết cũng dùng được nếu thực hiện đúng hợp đồng này. Xem [API Iterable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html).

### Iterable khác Iterator

- `Iterable` mô tả nguồn có thể cấp bộ lặp.
- `Iterator` mô tả trạng thái của một lần duyệt, với các thao tác như `hasNext()` và `next()`.

Một biến chỉ có kiểu `Iterator<String>` không phải một biểu thức nguồn for-each hợp lệ chỉ vì nó có `next()`:

```java
Iterator<String> iterator = List.of("An").iterator();
// for (String name : iterator) { } // Khong bien dich
```

Đây là đoạn minh họa; cần các import tương ứng. Khi đã chủ động quản lý một `Iterator`, có thể dùng vòng `while` và các thao tác bộ lặp thích hợp.

## 5. Kiểu biến lặp phải phù hợp với phần tử

Trình biên dịch kiểm tra việc một phần tử được đưa vào biến lặp. Không phải chọn kiểu bất kỳ đều hợp lệ.

| Nguồn | Khai báo biến lặp | Ý nghĩa |
| --- | --- | --- |
| `int[]` | `int value` | Nhận giá trị nguyên |
| `int[]` | `long value` | Nhận qua chuyển đổi mở rộng số nguyên |
| `String[]` | `String value` | Nhận tham chiếu chuỗi |
| `List<Integer>` | `Integer value` | Nhận đối tượng wrapper |
| `List<Integer>` | `int value` | Mở hộp từ `Integer` sang `int` |
| `List<Integer>` | `Number value` | Nhìn số nguyên qua kiểu cha `Number` |
| `List<?>` | `Object value` | Phần tử chưa biết kiểu cụ thể, dùng như `Object` |

Ví dụ sai:

```java
// for (String value : new int[] {1, 2}) { } // int khong tu doi thanh String
```

For-each không biến số thành văn bản và không bỏ qua kiểm tra kiểu.

### Mở hộp có thể gặp null

`List<Integer>` có thể chứa `null` nếu cách cài đặt và cách tạo danh sách cho phép. Khi lặp với `int value`, một phần tử `null` không thể được mở hộp và gây `NullPointerException`.

Nếu cần kiểm tra dữ liệu thiếu trước, dùng biến lặp `Integer`:

```java
for (Integer value : values) {
    if (value != null) {
        total += value;
    }
}
```

Đây là đoạn minh họa giả định `values` là một `Iterable<Integer>` và `total` là biến tổng bên ngoài. Việc bỏ qua `null` là một chính sách cụ thể; một ứng dụng khác có thể cần báo lỗi thay vì bỏ qua.

### Có thể dùng var khi kiểu vẫn dễ hiểu

Trong Java hiện nay:

```java
for (var word : List.of("java", "loop")) {
    System.out.println(word.length());
}
```

`word` được suy luận là `String` trong ví dụ này. `var` không làm biến đổi thành kiểu động; trình biên dịch vẫn xác định kiểu của nó.

Nếu nguồn là `List<?>`, `var` không tự đoán kiểu cụ thể của từng đối tượng runtime để cho gọi mọi phương thức riêng. Nó suy luận từ thông tin kiểu có sẵn tại mã nguồn.

## 6. Chương trình đầy đủ: mảng, Iterable và các tình huống cú pháp

Lưu thành `ForEachSyntaxDemo.java`:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ForEachSyntaxDemo {
    static final class LabelGroup implements Iterable<String> {
        private final List<String> labels;

        LabelGroup(List<String> labels) {
            this.labels = List.copyOf(labels);
        }

        @Override
        public Iterator<String> iterator() {
            return labels.iterator();
        }
    }

    static int[] makeValues() {
        System.out.println("source created");
        return new int[] {3, 5};
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30};
        int total = 0;
        for (int value : values) {
            total += value;
        }
        System.out.println("array sum = " + total);

        Iterable<String> names = List.of("An", "Binh");
        for (String name : names) {
            System.out.println("name = " + name);
        }

        for (String label : new LabelGroup(List.of("red", "blue"))) {
            System.out.println("label = " + label);
        }

        for (int value : makeValues()) {
            System.out.println("generated = " + value);
        }

        List<Integer> integers = List.of(2, 4, 6);
        int unboxedTotal = 0;
        for (int value : integers) {
            unboxedTotal += value;
        }
        System.out.println("unboxed sum = " + unboxedTotal);

        for (var word : List.of("java", "loop")) {
            System.out.println("word length = " + word.length());
        }

        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 8);
        scores.put("Binh", 9);
        for (Map.Entry<String, Integer> entry : scores.entrySet()) {
            System.out.println(entry.getKey() + " = " + entry.getValue());
        }

        int[][] matrix = {{1, 2}, {3}};
        int matrixTotal = 0;
        for (int[] row : matrix) {
            for (int value : row) {
                matrixTotal += value;
            }
        }
        System.out.println("matrix sum = " + matrixTotal);

        for (int value : values) {
            value = 0;
        }
        System.out.println("array after local assignment = "
                + Arrays.toString(values));

        List<StringBuilder> builders =
                List.of(new StringBuilder("a"), new StringBuilder("b"));
        for (StringBuilder builder : builders) {
            builder.append("!");
        }
        System.out.println("mutated objects = " + builders);

        for (int value : new int[] {1, 2, 3, 4, 5}) {
            if (value == 4) {
                break;
            }
            if (value == 2) {
                continue;
            }
            System.out.println("picked = " + value);
        }

        int visits = 0;
        for (String ignored : List.<String>of()) {
            visits++;
        }
        System.out.println("empty visits = " + visits);

        try {
            for (int value : Arrays.asList(1, null, 3)) {
                total += value;
            }
        } catch (NullPointerException exception) {
            System.out.println("unboxing null rejected");
        }

        int[] missing = null;
        try {
            for (int value : missing) {
                total += value;
            }
        } catch (NullPointerException exception) {
            System.out.println("null source rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ForEachSyntaxDemo.java
java ForEachSyntaxDemo
```

Stdout:

```text
array sum = 60
name = An
name = Binh
label = red
label = blue
source created
generated = 3
generated = 5
unboxed sum = 12
word length = 4
word length = 4
An = 8
Binh = 9
matrix sum = 6
array after local assignment = [10, 20, 30]
mutated objects = [a!, b!]
picked = 1
picked = 3
empty visits = 0
unboxing null rejected
null source rejected
```

### Lớp tự viết không cần là Collection

`LabelGroup` chỉ thực hiện `Iterable<String>` và cung cấp `iterator()`. Nó không cần kế thừa `ArrayList` hoặc thực hiện toàn bộ API của `Collection`.

Trong ví dụ, phương thức `iterator()` ủy quyền cho danh sách nhãn nội bộ. Vì danh sách được sao chép khi tạo nhóm, người gọi không dùng được danh sách nguồn để sửa cấu trúc bên trong sau đó.

Điều làm cho vòng lặp hợp lệ là hợp đồng `Iterable`, không phải tên lớp hay sự tồn tại ngẫu nhiên của một phương thức có tên `next`.

### Biểu thức nguồn được tính một lần khi vào vòng lặp

`makeValues()` in `source created` rồi trả mảng có hai phần tử. Dòng đó xuất hiện đúng một lần, sau đó hai phần tử được xử lý.

For-each không gọi lại `makeValues()` cho mỗi phần tử. Quy tắc này quan trọng khi biểu thức nguồn có chi phí hoặc tác dụng phụ.

Dù vậy, mã dễ đọc vẫn nên tránh gộp quá nhiều tác dụng phụ vào biểu thức nguồn khi có thể đặt tên biến rõ ràng trước vòng lặp.

## 7. Gán biến lặp không thay phần tử trong nguồn

Chương trình có:

```java
for (int value : values) {
    value = 0;
}
```

Sau đó, mảng vẫn là `[10, 20, 30]`.

`value` là biến cục bộ nhận bản sao của giá trị phần tử. Gán `0` cho biến không ghi ngược vào `values`.

Tương tự:

```java
String[] names = {"An", "Binh"};

for (String name : names) {
    name = "changed";
}
```

không thay hai tham chiếu được lưu ở các vị trí mảng.

Nếu muốn thay từng vị trí của mảng, dùng vòng lặp có chỉ số:

```java
for (int index = 0; index < values.length; index++) {
    values[index] = 0;
}
```

Đoạn này giả định `values` là mảng số nguyên đã có. Nó ghi trực tiếp vào từng phần tử của mảng.

### Thay trạng thái đối tượng là chuyện khác

Trong chương trình:

```java
for (StringBuilder builder : builders) {
    builder.append("!");
}
```

biến `builder` giữ tham chiếu tới đối tượng đang nằm trong danh sách. `append` sửa chính đối tượng đó, nên danh sách được in thành `[a!, b!]`.

Sự khác nhau là:

- Gán biến lặp sang một đối tượng khác chỉ đổi biến cục bộ.
- Gọi phương thức làm thay đổi đối tượng có thể ảnh hưởng đối tượng mà nguồn đang tham chiếu.

Một danh sách không cho thêm/xóa phần tử vẫn có thể chứa các đối tượng phần tử có trạng thái thay đổi được, như `StringBuilder` trong ví dụ.

## 8. Map không phải nguồn for-each trực tiếp

`Map<K,V>` không thực hiện `Iterable` để chọn sẵn việc duyệt khóa, giá trị hay cặp ánh xạ.

Vì vậy:

```java
// for (Object item : scores) { } // Khong bien dich neu scores la Map
```

Hãy chọn cách nhìn cần duyệt:

```java
for (String key : scores.keySet()) {
    System.out.println(key);
}

for (Integer score : scores.values()) {
    System.out.println(score);
}

for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + " = " + entry.getValue());
}
```

Các đoạn giả định `scores` là `Map<String, Integer>`. `keySet`, `values` và `entrySet` cung cấp các collection view phù hợp, theo [API Map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html).

Chương trình đầy đủ dùng `LinkedHashMap` để thứ tự xuất hiện của hai cặp dữ liệu ổn định theo thứ tự thêm. Không suy ra mọi loại `Map` đều có cùng thứ tự duyệt.

## 9. Các nguồn thường bị hiểu nhầm

### String không tự là Iterable<Character>

Không thể viết trực tiếp `for (char ch : text)` nếu `text` là `String`.

Nếu thực sự cần duyệt các đơn vị `char`, có thể dùng `text.toCharArray()`:

```java
for (char ch : "abc".toCharArray()) {
    System.out.println(ch);
}
```

`char` là đơn vị mã UTF-16, không bảo đảm tương ứng với một ký tự Unicode hoàn chỉnh mà người dùng nhìn thấy. Chọn cách duyệt Unicode là một yêu cầu dữ liệu riêng; for-each không tự giải quyết nó.

### Một phương thức iterator() có tên đúng chưa đủ

Một lớp không thực hiện `Iterable` không tự dùng được trong for-each chỉ vì có một phương thức tự đặt tên `iterator`. Java kiểm tra quan hệ kiểu đã được khai báo.

### Biến Object có thể che mất kiểu nguồn

Nếu một đối tượng mảng hoặc danh sách được giữ trong biến chỉ có kiểu `Object`, trình biên dịch không thể mặc định coi biểu thức đó là nguồn for-each phù hợp.

Cần giữ kiểu phù hợp trong API hoặc kiểm tra, thu hẹp kiểu theo hợp đồng trước khi duyệt. Không dùng ép kiểu tùy tiện để bỏ qua việc xác định nguồn.

## 10. Rỗng, null và điều khiển luồng

### Nguồn rỗng

Mảng có độ dài `0` hoặc `Iterable` không có phần tử khiến thân vòng lặp không được thực hiện lần nào. Đó là trạng thái hợp lệ, không phải lỗi.

### Nguồn null

Nếu chính mảng hoặc đối tượng `Iterable` là `null`, vòng lặp gặp `NullPointerException` khi bắt đầu duyệt. For-each không tự xem `null` là một tập hợp rỗng.

Cần quy định API trả nguồn rỗng hay cho phép thiếu nguồn; không tự gộp hai ý nghĩa nếu nghiệp vụ cần phân biệt.

### Phần tử null

Với biến lặp tham chiếu như `String name`, một phần tử `null` có thể được gán vào biến. Gọi `name.length()` sau đó sẽ lỗi nếu không kiểm tra.

Với biến primitive nhận wrapper qua mở hộp, lỗi có thể xảy ra ngay lúc phần tử `null` được gán cho biến lặp.

### break và continue

Trong chương trình:

- `value == 2` dẫn tới `continue`, bỏ phần còn lại của lượt đó.
- `value == 4` dẫn tới `break`, kết thúc vòng lặp.
- Vì vậy chỉ in `picked = 1` và `picked = 3`.

`return` trong thân vẫn kết thúc phương thức đang chứa vòng lặp theo quy tắc Java thông thường.

Câu lệnh `for (T item : source)` khác với lời gọi `source.forEach(...)` nhận một hàm. Không chuyển máy móc `break`, `continue` hoặc ý nghĩa `return` giữa hai cú pháp.

## 11. For-each không tự tạo snapshot hoặc bảo đảm an toàn luồng

Thứ tự và khả năng quan sát thay đổi phụ thuộc nguồn:

- Mảng đi theo chỉ số.
- `List` đi theo thứ tự duyệt của danh sách.
- Những nguồn không cam kết thứ tự không tự có thứ tự ổn định nhờ for-each.
- Cách xử lý thay đổi đồng thời phụ thuộc hợp đồng của nguồn và bộ lặp.

Không tự thêm hoặc xóa cấu trúc của một `ArrayList` qua tham chiếu danh sách ngay trong for-each rồi dựa vào việc “lần này chưa lỗi”. Một số bộ lặp có thể báo `ConcurrentModificationException`; hành vi phát hiện đó không phải cơ chế đồng bộ hoặc một bảo đảm phát hiện mọi sai lệch.

Nếu tác vụ là xóa theo điều kiện, cân nhắc API như `removeIf`. Nếu cần điều khiển chính bộ lặp và xóa qua nó, dùng `Iterator` tường minh theo hợp đồng của nguồn.

Những lựa chọn đó không làm for-each kém phù hợp cho việc đọc từng phần tử. Chúng cho thấy nên chọn kiểu vòng lặp theo thao tác thật sự cần thực hiện.

## 12. Khi nào nên chọn vòng lặp khác?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Xử lý lần lượt từng giá trị | For-each |
| Cần chỉ số để ghi lại từng ô mảng | `for` có chỉ số |
| Cần đi lùi hoặc nhảy bước theo vị trí | Vòng có chỉ số hoặc API duyệt phù hợp |
| Cần so sánh phần tử hiện tại với vị trí trước/sau | Chỉ số hoặc trạng thái duyệt tường minh |
| Cần điều khiển thao tác xóa qua bộ lặp | `Iterator` tường minh |
| Cần duyệt cặp khóa-giá trị của Map | For-each trên `entrySet()` |

For-each không mặc định nhanh hơn mọi vòng lặp khác. Giá trị chính của cú pháp là diễn tả rõ việc duyệt từng phần tử và tránh quản lý chỉ số khi không cần.

## 13. Tự kiểm tra

### Bài 1: Nguồn nào hợp lệ?

Xét `int[]`, `List<String>`, `Iterable<String>`, `Iterator<String>` và `Map<String, Integer>`.

**Đáp án:** ba kiểu đầu dùng được trực tiếp với for-each. Một `Iterator` đơn thuần và một `Map` không dùng trực tiếp theo cùng cách; cần chọn cách duyệt tương ứng.

### Bài 2: Thay giá trị mảng

Vì sao `for (int value : values) { value++; }` không tăng các phần tử trong mảng?

**Đáp án:** chỉ tăng biến cục bộ nhận giá trị của phần tử. Muốn sửa các vị trí mảng, phải ghi vào chúng, thường bằng chỉ số.

### Bài 3: Mở hộp

`for (int value : list)` có an toàn nếu `list` là `List<Integer>` có phần tử `null` không?

**Đáp án:** không. Mở hộp `null` gây `NullPointerException`. Dùng biến wrapper nếu cần xử lý `null` trước, rồi áp dụng chính sách phù hợp.

### Bài 4: Tính biểu thức nguồn

Với `for (int value : makeValues())`, hàm tạo nguồn có được gọi lại cho mỗi giá trị không?

**Đáp án:** không. Biểu thức nguồn được tính một lần khi bắt đầu vòng lặp đó.

### Bài 5: Lớp tự viết

`LabelGroup` phải kế thừa `ArrayList` để dùng for-each không?

**Đáp án:** không. Thực hiện `Iterable<String>` và cung cấp bộ lặp đúng hợp đồng là đủ.

Khi viết for-each, hãy xác định kiểu nguồn, kiểu phần tử và thao tác trong thân. Nếu chỉ cần đi qua từng phần tử, cú pháp này giữ ý định rõ ràng; nếu cần vị trí hoặc điều khiển cấu trúc đang duyệt, hãy chọn công cụ thể hiện đúng nhu cầu đó.
