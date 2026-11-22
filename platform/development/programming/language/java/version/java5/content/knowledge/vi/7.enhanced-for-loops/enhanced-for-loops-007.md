# Tác động của việc gán lại biến vòng lặp

## 1. Câu hỏi đầu tiên: đang sửa biến hay sửa dữ liệu nguồn?

Đoạn sau trông như đang tăng mọi phần tử của mảng:

```java
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    number += 10;
}
```

Nhưng sau vòng lặp, mảng vẫn là `[1, 2, 3]`.

`number` là **biến cục bộ của lượt lặp**, không phải một tên thay thế cho ô mảng hiện tại. Phần tử được đọc rồi dùng để khởi tạo biến; gán lại biến không tự ghi ngược về nguồn.

Cần phân biệt ba việc:

1. **Gán lại biến lặp:** thay giá trị mà biến cục bộ giữ.
2. **Thay phần tử trong container:** ghi vào ô mảng hoặc vị trí danh sách.
3. **Sửa trạng thái đối tượng:** thay nội dung của một đối tượng mà các tham chiếu cùng trỏ tới.

Chỉ hai việc sau có thể thay đổi dữ liệu mà người giữ nguồn quan sát được. Chúng cần một thao tác ghi thực sự vào cấu trúc hoặc đối tượng, không xuất hiện tự động từ phép gán biến lặp.

Đây là hành vi của for-each trong Java hiện nay, áp dụng cho cả mảng và các nguồn `Iterable`. Ví dụ đầy đủ bên dưới chạy với JDK 17 trở lên.

## 2. Phần tử được đưa vào biến lặp bằng giá trị

### Với kiểu nguyên thủy

`int` trong ô mảng là một giá trị số. Khi đến một lượt lặp:

```text
numbers[0] giu 1
        |
        | doc gia tri
        v
number giu 1
        |
        | number += 10
        v
number giu 11

numbers[0] van giu 1
```

Không có một liên kết ghi ngược từ biến `number` tới ô `numbers[0]`.

Những thao tác dưới đây đều chỉ thay biến cục bộ nếu vế trái là biến lặp:

```java
number = 0;
number++;
number *= 2;
```

Đây là các câu lệnh minh họa bên trong thân vòng lặp; không phải chương trình độc lập.

### Với kiểu tham chiếu

Khi phần tử là đối tượng, giá trị được sao chép vào biến là **tham chiếu** tới đối tượng, không phải một bản sao sâu của đối tượng đó.

Vì thế, ban đầu container và biến lặp có thể cùng trỏ tới một đối tượng. Nếu gán một tham chiếu mới cho biến lặp, ô của container vẫn giữ tham chiếu cũ.

Đây vẫn là sao chép giá trị tham chiếu. Không nên gọi đó là “biến lặp truyền tham chiếu ngược tới ô chứa”, vì phép gán biến lặp không sửa ô chứa.

## 3. Integer và String vẫn không được thay trong nguồn chỉ bằng gán biến

### 3.1. Integer: phép cộng không sửa đối tượng số nguyên

```java
List<Integer> values = new ArrayList<>(List.of(1, 2));

for (Integer value : values) {
    value += 10;
}
```

Đoạn minh họa cần import `List` và `ArrayList`. Danh sách sau vòng lặp vẫn là `[1, 2]`.

`Integer` là kiểu bất biến. `value += 10` làm việc qua các bước mở hộp, cộng và đóng hộp kết quả rồi gán kết quả cho biến cục bộ. Nó không đổi số `1` bên trong đối tượng `Integer` thành `11` và cũng không gọi `List.set`.

Không cần dựa vào việc các đối tượng wrapper có thể được dùng lại trong một số phạm vi giá trị. Vấn đề ở đây là vị trí được gán: biến lặp hay vị trí danh sách.

Nếu phần tử wrapper là `null`, phép toán cần mở hộp có thể gây `NullPointerException`. Việc biến lặp có kiểu tham chiếu không làm mọi thao tác số học tự xử lý được `null`.

### 3.2. String: tạo chuỗi kết quả không thay danh sách

```java
for (String name : names) {
    name = name.toUpperCase(Locale.ROOT);
}
```

Giả định `names` là một danh sách chuỗi khác `null` và có các import cần thiết.

`String` bất biến. Phép chuyển thành chữ hoa cung cấp một giá trị chuỗi kết quả; gán nó vào `name` không ghi kết quả vào danh sách `names`.

Tương tự, gọi `strip`, `replace` hoặc nối chuỗi rồi chỉ gán biến lặp cũng không thay tham chiếu được lưu tại vị trí nguồn.

### Gán null không xóa phần tử

```java
String[] values = {"A", "B"};

for (String value : values) {
    value = null;
}
```

Mảng vẫn chứa `"A"` và `"B"`. Chỉ biến cục bộ bị đổi thành `null` ở từng lượt.

Ngay cả khi ghi trực tiếp `values[0] = null`, mảng vẫn có cùng độ dài; một ô trở thành `null` không phải thao tác xóa và thu nhỏ mảng.

## 4. Sửa đối tượng có thể thay dữ liệu nguồn quan sát được

Với `StringBuilder`:

```java
for (StringBuilder builder : builders) {
    builder.append("!");
}
```

Giả định nguồn chứa các đối tượng khác `null`.

`append` sửa trạng thái của chính đối tượng đang được tham chiếu. Vì container vẫn giữ tham chiếu tới đối tượng đó, khi in container ta thấy nội dung mới.

Mô hình:

```text
builders[0] ------+
                  |
                  v
            StringBuilder("a")
                  ^
                  |
builder ----------+

builder.append("!") sua doi tuong chung thanh "a!"
```

Ngược lại:

```java
for (StringBuilder builder : builders) {
    builder = new StringBuilder("replacement");
}
```

chỉ làm `builder` trỏ tới đối tượng mới. `builders[0]` vẫn trỏ tới đối tượng ban đầu.

### Vế trái của phép gán cho biết vị trí đang được ghi

| Câu lệnh | Thứ thực sự bị thay đổi |
| --- | --- |
| `builder = another` | Biến lặp cục bộ |
| `builders[index] = another` | Ô mảng |
| `list.set(index, another)` | Vị trí trong danh sách |
| `builder.append("!")` | Trạng thái đối tượng được tham chiếu |
| `person.setName("An")` | Trạng thái đối tượng, nếu phương thức thực sự sửa nó |

Không chỉ nhìn việc “có dấu `=`” hay “có gọi phương thức” để kết luận. Cần biết thao tác đó ghi vào biến, container hay đối tượng nào.

## 5. Chương trình đầy đủ: đặt các trường hợp cạnh nhau

Lưu thành `ForEachReassignmentDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class ForEachReassignmentDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        for (int number : numbers) {
            number += 10;
        }
        System.out.println("primitive after local change = "
                + Arrays.toString(numbers));

        for (int index = 0; index < numbers.length; index++) {
            numbers[index] += 10;
        }
        System.out.println("primitive after indexed change = "
                + Arrays.toString(numbers));

        List<Integer> boxed = new ArrayList<>(List.of(1, 2));
        for (Integer number : boxed) {
            number += 10;
        }
        System.out.println("boxed after local change = " + boxed);

        ListIterator<Integer> cursor = boxed.listIterator();
        while (cursor.hasNext()) {
            Integer current = cursor.next();
            cursor.set(current + 10);
        }
        System.out.println("boxed after iterator set = " + boxed);

        List<String> names = new ArrayList<>(List.of("an", "binh"));
        for (String name : names) {
            name = name.toUpperCase(Locale.ROOT);
        }
        System.out.println("names after local change = " + names);
        names.replaceAll(name -> name.toUpperCase(Locale.ROOT));
        System.out.println("names after replaceAll = " + names);

        StringBuilder[] builders = {
                new StringBuilder("a"),
                new StringBuilder("b")
        };
        for (StringBuilder builder : builders) {
            builder = new StringBuilder("replacement");
        }
        System.out.println("builders after reassign = "
                + Arrays.toString(builders));

        for (StringBuilder builder : builders) {
            builder.append("!");
        }
        System.out.println("builders after mutation = "
                + Arrays.toString(builders));

        for (final StringBuilder builder : builders) {
            builder.append("?");
        }
        System.out.println("builders with final variable = "
                + Arrays.toString(builders));

        StringBuilder shared = new StringBuilder("x");
        List<StringBuilder> aliases = List.of(shared, shared);
        for (StringBuilder builder : aliases) {
            builder.append("+");
        }
        System.out.println("shared object = " + shared);
        System.out.println("alias list = " + aliases);

        int[][] matrix = {{1, 2}, {3, 4}};
        for (int[] row : matrix) {
            row = new int[] {0, 0};
        }
        System.out.println("matrix after row reassign = "
                + Arrays.deepToString(matrix));

        for (int[] row : matrix) {
            row[0] += 10;
        }
        System.out.println("matrix after row mutation = "
                + Arrays.deepToString(matrix));

        String[] values = {"A", "B"};
        for (String value : values) {
            value = null;
        }
        System.out.println("array after local null = "
                + Arrays.toString(values));

        try {
            List.of("fixed").replaceAll(
                    value -> value.toUpperCase(Locale.ROOT));
        } catch (UnsupportedOperationException exception) {
            System.out.println("unmodifiable list rejected replacement");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ForEachReassignmentDemo.java
java ForEachReassignmentDemo
```

Stdout:

```text
primitive after local change = [1, 2, 3]
primitive after indexed change = [11, 12, 13]
boxed after local change = [1, 2]
boxed after iterator set = [11, 12]
names after local change = [an, binh]
names after replaceAll = [AN, BINH]
builders after reassign = [a, b]
builders after mutation = [a!, b!]
builders with final variable = [a!?, b!?]
shared object = x++
alias list = [x++, x++]
matrix after row reassign = [[1, 2], [3, 4]]
matrix after row mutation = [[11, 2], [13, 4]]
array after local null = [A, B]
unmodifiable list rejected replacement
```

Các ví dụ số học dùng giá trị nhỏ để tập trung vào nơi được cập nhật. Trong tác vụ thực tế, vẫn cần lựa chọn kiểu số và quy tắc tràn phù hợp.

## 6. Muốn thay phần tử của mảng: ghi vào chỉ số

Cách rõ ràng:

```java
for (int index = 0; index < numbers.length; index++) {
    numbers[index] += 10;
}
```

Trong chương trình, đây là lần làm mảng đổi từ `[1, 2, 3]` thành `[11, 12, 13]`.

Biến `index` xác định ô cần ghi. Vế trái `numbers[index]` là phần tử nguồn, nên phép cập nhật tác động đúng nơi cần thay đổi.

Nếu muốn thay mỗi phần tử tham chiếu bằng một đối tượng mới, cũng phải ghi vào ô đó:

```java
for (int index = 0; index < builders.length; index++) {
    builders[index] = new StringBuilder("replacement");
}
```

Đây là đoạn thay thế minh họa cho một mảng `StringBuilder[]` có sẵn. Nó khác hẳn việc chỉ gán `builder` trong for-each.

Không cần cố nhét một biến đếm thủ công vào thân for-each nếu toàn bộ tác vụ vốn phụ thuộc vị trí. Một vòng lặp có chỉ số thường diễn tả ý định tốt hơn.

## 7. Muốn thay phần tử List: dùng thao tác của List hoặc ListIterator

### 7.1. ListIterator.set thay phần tử vừa được trả về

Chương trình dùng:

```java
ListIterator<Integer> cursor = boxed.listIterator();

while (cursor.hasNext()) {
    Integer current = cursor.next();
    cursor.set(current + 10);
}
```

`set` ghi vào vị trí của phần tử vừa được `next` trả về, không chỉ thay một biến cục bộ.

Đối với `ArrayList` trong ví dụ, kết quả là `[11, 12]`.

Thao tác `set` là khả năng tùy chọn của `ListIterator`. Nó yêu cầu trạng thái sử dụng phù hợp; ví dụ gọi sau `next` và không xen `remove` hoặc `add` làm mất hiệu lực của phần tử cần thay.

Một `Iterator` cơ bản không có `set`. Không thể sửa lỗi gán biến bằng cách gọi một phương thức mà hợp đồng bộ lặp không cung cấp.

Xem [ListIterator.set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html#set(E)).

### 7.2. replaceAll diễn tả việc biến đổi từng phần tử

Với danh sách chuỗi:

```java
names.replaceAll(name -> name.toUpperCase(Locale.ROOT));
```

Mỗi giá trị hàm trả về được dùng để thay phần tử tương ứng trong danh sách. Kết quả không chỉ nằm trong một biến lặp rồi bị bỏ đi.

Trong ví dụ, `[an, binh]` trở thành `[AN, BINH]`.

`Locale.ROOT` được dùng để phép đổi chữ hoa không phụ thuộc locale mặc định của máy trong những chuỗi minh họa này.

Phương thức đòi danh sách hỗ trợ thay thế phần tử. Một danh sách tạo bằng `List.of` không hỗ trợ, nên chương trình bắt được `UnsupportedOperationException`.

`replaceAll` không tự biến một danh sách không cho sửa thành danh sách có thể sửa. Nó cũng không phải một giao dịch có hoàn tác mọi phần tử nếu hàm chuyển đổi lỗi giữa chừng.

Hợp đồng nằm ở [List.replaceAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)).

### 7.3. Có thể tạo kết quả mới thay vì sửa nguồn

Nếu yêu cầu là giữ nguyên nguồn, hãy xây một danh sách kết quả:

```java
List<String> upperNames = new ArrayList<>();
for (String name : names) {
    upperNames.add(name.toUpperCase(Locale.ROOT));
}
```

Đoạn giả định nguồn chứa các chuỗi khác `null`. For-each vẫn phù hợp vì nhiệm vụ ở đây là đọc từng giá trị và đưa kết quả sang cấu trúc khác.

Không phải cứ thấy nguồn không đổi là lỗi. Cần đối chiếu với mục tiêu: sửa tại chỗ hay tạo dữ liệu mới.

## 8. Mảng hai chiều làm rõ hai cấp tham chiếu

Mảng `int[][]` là một mảng có phần tử là các tham chiếu `int[]`.

Trong chương trình:

```java
for (int[] row : matrix) {
    row = new int[] {0, 0};
}
```

không thay các hàng được lưu trong `matrix`. Chỉ biến `row` nhận tham chiếu tới một mảng hàng mới.

Còn:

```java
for (int[] row : matrix) {
    row[0] += 10;
}
```

sửa ô đầu của từng đối tượng mảng hàng mà `matrix` đang tham chiếu.

Do đó:

- Sau gán lại `row`, ma trận vẫn là `[[1, 2], [3, 4]]`.
- Sau sửa `row[0]`, ma trận là `[[11, 2], [13, 4]]`.

Nếu thật sự muốn thay toàn bộ hàng, cần viết `matrix[index] = newRow`. Nếu chỉ muốn thay giá trị bên trong hàng, có thể dùng tham chiếu `row` để ghi các ô của hàng.

Ví dụ có các hàng khác `null` và không rỗng. Với ma trận tổng quát, phải kiểm tra điều kiện đó trước khi truy cập `row[0]`.

## 9. Nhiều phần tử có thể cùng tham chiếu một đối tượng

Chương trình tạo:

```java
StringBuilder shared = new StringBuilder("x");
List<StringBuilder> aliases = List.of(shared, shared);
```

Danh sách có hai vị trí nhưng cả hai giữ cùng một tham chiếu.

Khi for-each duyệt mỗi vị trí và gọi `append("+")`:

1. Lượt đầu sửa đối tượng chung từ `x` thành `x+`.
2. Lượt thứ hai lại sửa chính đối tượng đó thành `x++`.
3. Cả hai vị trí khi in đều cho thấy `x++`.

Đây không phải for-each tự lặp sai phần tử. Nó đã duyệt hai vị trí đúng như nguồn cung cấp; hai vị trí tình cờ cùng trỏ tới một đối tượng.

Điểm này quan trọng khi xử lý các đối tượng có thể thay đổi: số lượt duyệt không đồng nghĩa số đối tượng khác nhau được sửa.

Danh sách `List.of` không cho thay đổi cấu trúc hoặc thay phần tử, nhưng không khóa trạng thái bên trong từng `StringBuilder`.

## 10. final trên biến lặp chỉ cấm gán lại biến

Có thể viết:

```java
for (final StringBuilder builder : builders) {
    builder.append("?");
}
```

Đoạn này vẫn sửa đối tượng, như stdout `[a!?, b!?]` của chương trình.

`final` ngăn gán một tham chiếu khác cho biến `builder` trong lượt lặp:

```java
// builder = new StringBuilder("other"); // Khong bien dich neu builder la final
```

Nó không làm đối tượng `StringBuilder` trở nên bất biến.

Với primitive, `final int value` cũng ngăn các phép gán như `value++` hoặc `value = 0` đối với biến đó. Điều này không tự làm mảng nguồn trở thành một mảng không cho sửa qua các tham chiếu khác.

Khai báo `final` trong for-each vẫn hợp lệ vì mỗi lượt có sự khởi tạo biến theo quy tắc của vòng lặp. Không được hiểu đây là cùng một biến final bị mã người dùng gán lại nhiều lần trong thân.

Quy tắc cơ sở về final nằm ở [JLS: final Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4).

## 11. Gán lại biến lặp có thể có chủ đích

Đoạn sau có thể hoàn toàn phù hợp nếu chỉ muốn in một cách nhìn đã làm sạch:

```java
for (String name : names) {
    name = name.strip();
    System.out.println(name);
}
```

Nó xử lý giá trị cục bộ cho công việc hiện tại và giữ nguyên danh sách.

Một cách diễn đạt khác dễ thấy ý định hơn là giữ hai tên:

```java
for (String name : names) {
    String cleaned = name.strip();
    System.out.println(cleaned);
}
```

Cả hai đều giả định phần tử khác `null`. Điểm cần xác định không phải “cấm gán biến lặp”, mà là liệu thay đổi cục bộ có đúng với mục tiêu hay không.

Nếu muốn ghi lại giá trị `cleaned` vào nguồn, cần một thao tác thay phần tử rõ ràng như những phần trước.

## 12. Đừng nhầm gán biến với thay đổi cấu trúc đang duyệt

`value = null` chỉ gán biến. Nó không xóa phần tử.

Gọi `list.remove(...)` là một thao tác khác: thay đổi cấu trúc container. Thực hiện nó trực tiếp trong for-each trên một số danh sách có thể vi phạm hợp đồng bộ lặp và gây lỗi.

Nếu mục tiêu là xóa theo điều kiện, dùng thao tác xóa phù hợp như `removeIf` hoặc điều khiển `Iterator.remove` theo hợp đồng của nguồn.

Nếu mục tiêu là thay thế từng phần tử, dùng `replaceAll`, `ListIterator.set` hoặc ghi theo chỉ số khi phù hợp.

Không chọn công cụ chỉ vì nó “làm nguồn đổi được”. Thay thế, xóa và sửa trạng thái đối tượng có ý nghĩa khác nhau.

## 13. Cách tự phân tích một vòng lặp

Khi kết quả không như mong muốn, lần lượt trả lời:

1. Nguồn giữ primitive hay tham chiếu?
2. Biến lặp nhận giá trị nào tại lượt hiện tại?
3. Vế trái của phép gán nằm ở đâu?
4. Có phương thức nào thực sự ghi vào container hoặc đối tượng không?
5. Có nhiều tham chiếu cùng trỏ tới đối tượng bị sửa không?
6. Nguồn có hỗ trợ thao tác thay thế hoặc xóa mong muốn không?
7. Ý định là sửa nguồn hay tạo kết quả mới?

Các quy tắc khởi tạo biến và duyệt nguồn xuất phát từ [JLS: The enhanced for statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2). Không có một bước “ghi ngược biến lặp về nguồn” tự động khi thân vòng lặp kết thúc.

## 14. Thực hành tự kiểm tra

### Bài 1: Primitive

`for (int value : values) { value *= 2; }` có nhân đôi các phần tử mảng không?

**Đáp án:** không. Nó chỉ sửa biến cục bộ. Muốn sửa mảng, ghi vào `values[index]`.

### Bài 2: Wrapper

Với `List<Integer>`, `value++` trong for-each có gọi ngầm `List.set` không?

**Đáp án:** không. Nó tính kết quả số và gán lại biến lặp; danh sách giữ các tham chiếu cũ.

### Bài 3: Đối tượng có thể thay đổi

`builder.append("!")` và `builder = new StringBuilder("!")` khác nhau ở đâu?

**Đáp án:** thao tác đầu sửa đối tượng chung; thao tác sau đổi tham chiếu trong biến lặp. Nó không thay ô chứa tham chiếu ban đầu.

### Bài 4: final

`final StringBuilder builder` có ngăn `append` không?

**Đáp án:** không. Nó ngăn gán lại biến, không khóa đối tượng.

### Bài 5: Mảng hai chiều

`row = new int[2]` và `row[0] = 0` có cùng tác động không?

**Đáp án:** không. Một câu lệnh đổi biến hàng cục bộ; câu kia ghi vào đối tượng mảng hàng mà biến đang tham chiếu.

### Bài 6: Danh sách không cho sửa

Gán biến lặp không thay danh sách, vậy chỉ cần gọi `replaceAll` trên mọi `List` là đúng không?

**Đáp án:** không. Danh sách phải hỗ trợ thay phần tử. Với `List.of` trong ví dụ, thao tác bị từ chối bằng `UnsupportedOperationException`.

Hãy luôn xác định chính xác nơi được ghi: biến lặp, vị trí trong container hay trạng thái của một đối tượng. Phân biệt ba vị trí này giúp dự đoán đúng tác động của for-each và chọn cách cập nhật có chủ đích.
