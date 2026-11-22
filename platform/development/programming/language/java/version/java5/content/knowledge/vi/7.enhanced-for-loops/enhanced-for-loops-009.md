# Giới hạn khi cần chỉ số, duyệt ngược hoặc xóa phần tử

## 1. For-each phù hợp với việc xử lý từng phần tử

Vòng lặp for-each giúp viết ngắn khi cần đi qua các phần tử theo thứ tự duyệt của nguồn:

```java
// Minh họa trong một phương thức; cần import java.util.List.
List<String> names = List.of("Lan", "Minh", "An");

for (String name : names) {
    System.out.println(name);
}
```

Nhưng biến `name` chỉ cung cấp giá trị phần tử ở lượt hiện tại. Cú pháp không đưa ra một biến chỉ số và cũng không đưa iterator của vòng lặp cho người viết sử dụng.

Ba yêu cầu thường cần chọn công cụ khác:

- Cần biết hoặc điều khiển vị trí.
- Cần duyệt theo chiều ngược.
- Cần xóa phần tử trong khi đang duyệt.

Đây là giới hạn của mức điều khiển mà cú pháp cung cấp, không có nghĩa for-each không được dùng `break` hoặc `continue`. Hai lệnh đó vẫn có ý nghĩa bình thường trong thân vòng lặp.

Các cách duyệt theo chỉ số và iterator trong bài vẫn áp dụng trong Java hiện đại. Ví dụ chính chạy trên Java 17 trở lên; một phần riêng trình bày API đảo chiều có từ Java 21.

## 2. Cơ chế giải thích những giới hạn này

Với mảng, Java có thể diễn giải for-each theo dạng dùng một chỉ số ẩn để lần lượt lấy phần tử. Người viết không truy cập được chỉ số ẩn ấy qua biến vòng lặp.

Với một nguồn `Iterable` như `ArrayList`, cơ chế tương đương sử dụng iterator để lấy từng phần tử. Iterator được quản lý bên trong cấu trúc vòng lặp; cú pháp for-each không đặt tên để người viết gọi `remove()` trên chính iterator đó.

Vì vậy, không nên cố biến biến phần tử thành:

- Một chỉ số.
- Một “con trỏ” có thể xóa phần tử.
- Một tham chiếu có thể gán lại để thay phần tử trong nguồn.

Muốn điều khiển những khả năng này, chọn một cấu trúc thể hiện chúng rõ ràng.

## 3. Khi cần chỉ số: dùng vòng lặp có vị trí rõ ràng

Với mảng:

```java
// Minh họa trong một phương thức.
int[] values = {10, 20, 30};

for (int i = 0; i < values.length; i++) {
    System.out.println(i + ":" + values[i]);
}
```

Với danh sách hỗ trợ truy cập theo vị trí hiệu quả, chẳng hạn `ArrayList`:

```java
// Minh họa trong một phương thức.
List<String> names = new ArrayList<>(List.of("Lan", "Minh", "An"));

for (int i = 0; i < names.size(); i++) {
    System.out.println(i + ":" + names.get(i));
}
```

Không lấy vị trí hiện tại bằng `names.indexOf(name)` trong for-each. Nếu có các giá trị bằng nhau, `indexOf` trả vị trí đầu tiên phù hợp, không nhất thiết là vị trí đang duyệt. Ngoài ra, tìm lại từ đầu cho mỗi phần tử có thể làm tăng chi phí đáng kể.

Có thể tự đếm một biến bên ngoài for-each nếu chỉ cần đánh số khi hiển thị, nhưng phải tự duy trì nó và chú ý các nhánh `continue`. Khi thuật toán thực sự cần chỉ số để đọc/ghi các vị trí, vòng lặp theo chỉ số thường thể hiện ý định rõ hơn.

### Không mặc định mọi List có chi phí get giống nhau

`ArrayList.get(i)` hỗ trợ truy cập ngẫu nhiên hiệu quả. Với danh sách liên kết, lặp lại `get(i)` cho từng vị trí có thể phải đi qua nhiều nút và khiến một lượt duyệt trở nên tốn kém.

Nếu cần cả phần tử lẫn vị trí mà không muốn dựa vào khả năng truy cập ngẫu nhiên, có thể dùng `ListIterator`:

```java
// Minh họa trong một phương thức; cần import java.util.ListIterator.
ListIterator<String> iterator = names.listIterator();

while (iterator.hasNext()) {
    int index = iterator.nextIndex();
    String name = iterator.next();
    System.out.println(index + ":" + name);
}
```

`nextIndex()` ở đây được gọi trước `next()`, nên nó mô tả vị trí phần tử sắp được trả về.

## 4. Gán lại biến for-each không thay phần tử trong nguồn

Ví dụ sau biên dịch được nhưng không nhân các phần tử của mảng:

```java
// Minh họa trong một phương thức.
int[] values = {1, 2, 3};

for (int value : values) {
    value = value * 10;
}
```

Biến `value` nhận một giá trị ở từng lượt; gán lại biến không ghi vào ô tương ứng trong mảng. Mảng vẫn là `[1, 2, 3]`.

Muốn thay các phần tử:

```java
// Minh họa trong một phương thức có mảng values.
for (int i = 0; i < values.length; i++) {
    values[i] = values[i] * 10;
}
```

Với danh sách, có thể dùng `set(i, newValue)` khi thích hợp, hoặc `ListIterator.set(...)` nếu đang duyệt bằng list iterator và thao tác được hỗ trợ.

Nếu phần tử là đối tượng thay đổi được, gọi phương thức sửa trạng thái của đối tượng ấy có thể làm nó thay đổi. Điều đó khác với gán biến vòng lặp sang một đối tượng khác, và cũng khác với thêm/xóa phần tử của collection.

## 5. Khi cần duyệt ngược

For-each không có cú pháp trực tiếp chọn chỉ số bắt đầu, bước nhảy âm hoặc hướng duyệt. Với một `List` thông thường, nó đi theo thứ tự mà iterator của danh sách cung cấp.

### 5.1. Mảng hoặc danh sách truy cập theo chỉ số hiệu quả

```java
// Minh họa trong một phương thức có mảng values.
for (int i = values.length - 1; i >= 0; i--) {
    System.out.println(values[i]);
}
```

Với `ArrayList`, có thể dùng `i = names.size() - 1`, điều kiện `i >= 0`, rồi giảm `i`.

Điều kiện `i >= 0` là cần thiết để xử lý cả phần tử đầu. Nếu nguồn rỗng, giá trị bắt đầu là `-1` và vòng lặp không chạy.

### 5.2. ListIterator đi từ cuối danh sách

```java
// Minh họa trong một phương thức; cần import java.util.ListIterator.
ListIterator<String> iterator = names.listIterator(names.size());

while (iterator.hasPrevious()) {
    String name = iterator.previous();
    System.out.println(name);
}
```

Vị trí `names.size()` đặt con trỏ sau phần tử cuối. Gọi `previous()` lần đầu sẽ trả phần tử cuối, không phải một phần tử ngoài phạm vi.

Cách này phù hợp khi muốn đi ngược mà không lặp lại thao tác truy cập ngẫu nhiên vào một danh sách liên kết.

### 5.3. Java 21 trở lên: duyệt cách nhìn đảo thứ tự

Java 21 bổ sung `List.reversed()`, trả về một cách nhìn có thứ tự ngược của danh sách. Nhờ đó có thể giữ cú pháp for-each:

```java
// Minh họa yêu cầu Java 21+.
for (String name : names.reversed()) {
    System.out.println(name);
}
```

Không phải bản thân for-each đã có tham số “đi ngược”; nguồn được truyền cho nó cung cấp thứ tự đảo.

`reversed()` trả về một view, không hứa tạo bản sao độc lập. Nếu view hỗ trợ sửa đổi, các thay đổi qua view có thể ghi về danh sách gốc theo hợp đồng API. Không sửa cấu trúc tùy ý qua danh sách gốc hoặc view khi đang dùng for-each để duyệt nó.

Nếu môi trường là Java 17, dùng vòng lặp chỉ số hoặc `ListIterator` phù hợp thay vì gọi API chưa có trong phiên bản ấy.

## 6. Xóa trực tiếp từ collection trong for-each là một lỗi thiết kế phổ biến

Ví dụ không nên dùng:

```java
// Minh họa không an toàn cho cách duyệt ArrayList này.
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

for (Integer value : values) {
    if (value % 2 == 0) {
        values.remove(value);
    }
}
```

For-each đang dùng một iterator nội bộ. Lời gọi `values.remove(value)` sửa cấu trúc danh sách qua một đường khác, không phải thao tác xóa của chính iterator đó.

Với các iterator fail-fast như của `ArrayList`, việc này có thể bị phát hiện và báo `ConcurrentModificationException`. Tên ngoại lệ không có nghĩa chắc chắn phải có hai luồng; một luồng tự sửa collection trong lúc iterator đang hoạt động cũng có thể vi phạm cách sử dụng.

Không nên dựa vào ngoại lệ để điều khiển thuật toán hoặc cho rằng mọi trường hợp sửa sai đều chắc chắn ném ngoại lệ. Cơ chế fail-fast chỉ phát hiện lỗi theo khả năng của bản triển khai; các collection khác cũng có hợp đồng duyệt khác nhau.

Không có stdout chuẩn cho đoạn không an toàn trên để dùng làm tiêu chí đúng. Hãy thay bằng một cách xóa được hợp đồng hỗ trợ.

## 7. Cách xóa phù hợp trong khi duyệt

### 7.1. Iterator.remove: xóa phần tử vừa được iterator trả về

```java
// Minh họa trong một phương thức; cần import java.util.Iterator.
Iterator<Integer> iterator = values.iterator();

while (iterator.hasNext()) {
    Integer value = iterator.next();
    if (value % 2 == 0) {
        iterator.remove();
    }
}
```

Ở đây thuật toán sở hữu rõ iterator đang duyệt và gọi xóa trên chính nó.

Các điều kiện cần nhớ:

- Phải có một lần `next()` hợp lệ trước khi xóa phần tử tương ứng.
- Không gọi `remove()` hai lần cho cùng một lần lấy phần tử.
- Iterator phải hỗ trợ thao tác xóa; đây là thao tác tùy chọn.
- Không đồng thời thêm/xóa qua các tham chiếu khác trái với hợp đồng của iterator.

Nếu dùng `ListIterator` đi ngược, `remove()` có thể xóa phần tử vừa được `previous()` trả về. Quy tắc vẫn dựa vào phần tử vừa được iterator trả về, không phải tự chọn một chỉ số bất kỳ.

### 7.2. removeIf: biểu diễn trực tiếp điều kiện cần xóa

```java
// Minh họa trong một phương thức có danh sách thay đổi được.
values.removeIf(value -> value % 2 == 0);
```

Khi yêu cầu chỉ là “xóa các phần tử thỏa điều kiện”, cách này thường dễ đọc hơn một vòng lặp quản lý iterator bằng tay.

Danh sách phải hỗ trợ thao tác xóa phù hợp; predicate không nên tự thêm/xóa collection đang được xử lý. `removeIf` không làm một danh sách từ `List.of` trở nên thay đổi được.

### 7.3. Duyệt chỉ số từ cuối khi xóa trên ArrayList

```java
// Minh họa trong một phương thức có ArrayList<Integer>.
for (int i = values.size() - 1; i >= 0; i--) {
    if (values.get(i) % 2 == 0) {
        values.remove(i);
    }
}
```

Xóa tại vị trí `i` làm các phần tử phía sau dịch chuyển. Vì chúng đã được xét khi đi từ cuối về đầu, những vị trí còn phải xét ở phía trước vẫn hợp lệ.

Đây là một lựa chọn đúng về điều khiển chỉ số trong ví dụ, nhưng không bảo đảm tối ưu cho mọi danh sách. Việc xóa nhiều vị trí trên `ArrayList` vẫn có thể cần dịch chuyển phần tử; với yêu cầu xóa theo điều kiện, nên cân nhắc `removeIf` thay vì mặc định một vòng lặp chỉ số luôn tốt hơn.

## 8. Lỗi bỏ sót khi xóa theo chỉ số tăng dần

Đoạn sau cũng sai dù không dùng for-each:

```java
// Minh họa lỗi logic.
List<Integer> values = new ArrayList<>(List.of(2, 4, 6));

for (int i = 0; i < values.size(); i++) {
    if (values.get(i) % 2 == 0) {
        values.remove(i);
    }
}
```

Kết quả còn `[4]`:

1. Xóa `2` ở vị trí `0`, danh sách thành `[4, 6]`.
2. `i` tăng lên `1`, nên phần tử `4` vừa dịch về vị trí `0` bị bỏ qua.
3. Xóa `6` ở vị trí `1`, còn `[4]`.

Vấn đề là chỉ số đã dịch chuyển, không phải một ngoại lệ bắt buộc phải xảy ra. Duyệt ngược, dùng iterator hoặc `removeIf` giúp diễn đạt điều khiển phù hợp hơn.

Với `List<Integer>`, còn phải phân biệt `remove(int index)` và `remove(Object value)`. Trong vòng lặp chỉ số ở trên, `remove(i)` cố ý là xóa theo vị trí.

## 9. Mảng và collection không có cùng khả năng xóa

Mảng có độ dài cố định. Không có thao tác `remove` làm một mảng đang tồn tại ngắn đi.

Nếu cần loại phần tử khỏi mảng, hãy xác định rõ yêu cầu: tạo một mảng mới chỉ chứa phần tử cần giữ, hoặc dùng một cấu trúc collection phù hợp trong giai đoạn xử lý. Việc gán biến for-each thành `null` hay `0` không xóa vị trí trong mảng.

Với collection, thao tác xóa còn phụ thuộc bản triển khai:

- `ArrayList` hỗ trợ xóa.
- Danh sách tạo bởi `List.of` không cho sửa.
- Một số cách nhìn hoặc iterator có thể không hỗ trợ thao tác xóa tùy chọn.

Đổi cú pháp vòng lặp không thay đổi hợp đồng sửa đổi của nguồn.

## 10. Chương trình đầy đủ trên Java 17+

Lưu vào `ForEachLimitsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;

public class ForEachLimitsDemo {
    public static void main(String[] args) {
        int[] values = {1, 2, 3};
        for (int value : values) {
            value = value * 10;
        }
        System.out.println(Arrays.toString(values));

        for (int i = 0; i < values.length; i++) {
            values[i] = values[i] * 10;
        }
        System.out.println(Arrays.toString(values));

        List<String> names =
                new ArrayList<>(List.of("Lan", "Minh", "An"));
        for (int i = 0; i < names.size(); i++) {
            System.out.println(i + ":" + names.get(i));
        }

        List<String> reverseOrder = new ArrayList<>();
        ListIterator<String> reverse =
                names.listIterator(names.size());
        while (reverse.hasPrevious()) {
            reverseOrder.add(reverse.previous());
        }
        System.out.println(reverseOrder);

        List<Integer> byIterator =
                new ArrayList<>(List.of(1, 2, 3, 4));
        Iterator<Integer> iterator = byIterator.iterator();
        while (iterator.hasNext()) {
            Integer value = iterator.next();
            if (value % 2 == 0) {
                iterator.remove();
            }
        }
        System.out.println(byIterator);

        List<Integer> byCondition =
                new ArrayList<>(List.of(1, 2, 3, 4));
        byCondition.removeIf(value -> value % 2 == 0);
        System.out.println(byCondition);

        List<Integer> backwards =
                new ArrayList<>(List.of(2, 4, 6));
        for (int i = backwards.size() - 1; i >= 0; i--) {
            if (backwards.get(i) % 2 == 0) {
                backwards.remove(i);
            }
        }
        System.out.println(backwards);

        List<Integer> skipped =
                new ArrayList<>(List.of(2, 4, 6));
        for (int i = 0; i < skipped.size(); i++) {
            if (skipped.get(i) % 2 == 0) {
                skipped.remove(i);
            }
        }
        System.out.println(skipped);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ForEachLimitsDemo.java
java ForEachLimitsDemo
```

Stdout chính xác:

```text
[1, 2, 3]
[10, 20, 30]
0:Lan
1:Minh
2:An
[An, Minh, Lan]
[1, 3]
[1, 3]
[]
[4]
```

Dòng đầu cho thấy gán biến for-each không ghi vào mảng; dòng thứ hai dùng chỉ số để cập nhật mảng. Hai danh sách `[1, 3]` được tạo bằng hai cách xóa được hỗ trợ. Hai dòng cuối đối chiếu cách xóa ngược đúng với cách tăng chỉ số làm bỏ sót phần tử.

Đoạn `skipped` cố ý giữ lỗi logic để quan sát, không phải mẫu nên dùng trong ứng dụng.

## 11. Ví dụ riêng cho Java 21+: reversed view

Lưu vào `ReverseViewDemo.java` và dùng JDK 21 trở lên:

```java
import java.util.List;

public class ReverseViewDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3);

        for (int value : values.reversed()) {
            System.out.println(value);
        }

        System.out.println(values);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 ReverseViewDemo.java
java ReverseViewDemo
```

Stdout chính xác:

```text
3
2
1
[1, 2, 3]
```

Việc duyệt view đảo không tự đảo vị trí của danh sách gốc. Ví dụ không sửa đổi danh sách hoặc view; danh sách từ `List.of` không cho sửa.

## 12. Cách chọn công cụ và tự luyện

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Xử lý từng phần tử, không cần điều khiển vị trí | For-each |
| Cần chỉ số để đọc/ghi mảng | Vòng lặp chỉ số |
| Cần vị trí trên danh sách, không giả định truy cập ngẫu nhiên | `ListIterator` |
| Duyệt ngược một danh sách | `ListIterator`, hoặc view `reversed()` trên Java 21+ |
| Duyệt ngược mảng | Vòng lặp chỉ số giảm dần |
| Xóa phần tử thỏa điều kiện đơn giản | `removeIf` khi collection hỗ trợ |
| Duyệt kèm quyết định xóa ở từng bước | `Iterator.remove()` hoặc `ListIterator.remove()` khi được hỗ trợ |

Bài tập:

1. Tạo danh sách có phần tử trùng và giải thích vì sao `indexOf` trong for-each không thể hiện đúng mọi vị trí hiện tại.
2. Viết vòng lặp đi ngược với một danh sách rỗng, một phần tử và nhiều phần tử. Kiểm tra không truy cập chỉ số âm.
3. Thay điều kiện xóa số chẵn bằng điều kiện xóa chuỗi rỗng, dùng cả iterator và `removeIf`.
4. Duyệt ngược bằng `ListIterator` rồi xóa một số phần tử bằng chính iterator đó.
5. Giải thích vì sao đoạn xóa theo chỉ số tăng dần còn `[4]`, dù không phát sinh lỗi truy cập ngoài phạm vi.
6. So sánh duyệt `names.reversed()` trên Java 21 với việc tạo một bản sao riêng rồi đảo bản sao. Chúng có cùng hợp đồng chia sẻ dữ liệu không?
7. Một đoạn for-each tự xóa collection nhưng tình cờ không ném ngoại lệ trong lần chạy. Vì sao kết quả đó chưa chứng minh cách dùng đúng?

## Tài liệu đối chiếu

- [Java Language Specification — Enhanced for (§14.14.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2): cơ chế for-each với mảng và `Iterable`.
- [Java API — Iterator.remove](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html#remove()): điều kiện xóa phần tử vừa được trả về.
- [Java API — ListIterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html): duyệt hai chiều và thao tác theo iterator.
- [Java API — Collection.removeIf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)): xóa theo điều kiện.
- [Java API — ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): truy cập vị trí và cơ chế fail-fast.
- [Java API — List.reversed](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#reversed()): view đảo thứ tự, có từ Java 21.
