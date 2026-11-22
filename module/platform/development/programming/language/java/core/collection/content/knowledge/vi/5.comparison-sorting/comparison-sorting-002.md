# Comparator và hợp đồng dấu, tính bắc cầu, tính nhất quán

Một `Comparator<T>` trả lời câu hỏi: **theo một quy tắc đã chọn, đối tượng nào đứng trước, đối tượng nào đứng sau, và những đối tượng nào được xem là cùng hạng?**

Ví dụ, có thể xếp các mặt hàng theo điểm tăng dần, hoặc theo điểm giảm dần rồi đến mã tăng dần. Comparator mô tả quy tắc; thuật toán sắp xếp hoặc cấu trúc dữ liệu sử dụng quy tắc đó.

Điều quan trọng là comparator phải đưa ra những câu trả lời có thể phối hợp với nhau. Một lần so sánh đúng chưa đủ: kết quả phải hợp lý khi đổi chiều hai đối số, xét bộ ba đối tượng và thay một đối tượng bằng đối tượng được xem là cùng hạng.

## 1. Đọc đúng kết quả compare

Phương thức trung tâm có dạng:

```java
int compare(T x, T y);
```

Đây là chữ ký minh họa của phương thức trong interface, không phải chương trình độc lập.

| Kết quả | Ý nghĩa theo comparator |
| --- | --- |
| Nhỏ hơn 0 | `x` đứng trước `y` |
| Bằng 0 | `x` và `y` cùng hạng theo quy tắc |
| Lớn hơn 0 | `x` đứng sau `y` |

**Chỉ dấu của số trả về có ý nghĩa đối với thứ tự.** Comparator hợp lệ có thể trả `-7`, `0`, `12`; không bắt buộc trả đúng `-1`, `0`, `1`.

Khi diễn đạt hợp đồng, dùng hàm dấu:

```text
sign(n) = -1 nếu n < 0
sign(n) =  0 nếu n = 0
sign(n) =  1 nếu n > 0
```

Trong Java, `Integer.signum(result)` thực hiện việc chuẩn hóa này.

Vì vậy, bên sử dụng kiểm tra `compare(x, y) < 0`, không kiểm tra `compare(x, y) == -1`. Nếu muốn đảo thứ tự, hãy đảo quan hệ so sánh thay vì giả định giá trị tuyệt đối của kết quả.

## 2. Ba ràng buộc cốt lõi

Đặt `c(x, y)` là kết quả của `comparator.compare(x, y)`. Các ràng buộc xét trên miền đối tượng mà comparator chấp nhận.

### 2.1. Đổi chiều phải đổi dấu

```text
sign(c(x, y)) = -sign(c(y, x))
```

Nếu `x` đứng trước `y`, đổi chiều phải nói `y` đứng sau `x`. Nếu một chiều trả 0, chiều kia cũng phải trả 0.

Điều này là **đối xứng ngược về dấu**, không phải yêu cầu hai số nguyên trả về luôn là hai số đối nhau. Chẳng hạn, trả `-2` ở một chiều và `9` ở chiều kia vẫn thỏa điều kiện dấu.

Một hệ quả cần kiểm tra là `c(x, x) == 0`: một đối tượng không thể vừa đứng trước chính nó vừa tuân thủ quy tắc đổi dấu.

Nếu việc so sánh không được hỗ trợ và một chiều ném ngoại lệ, chiều đảo lại cũng phải ném ngoại lệ. Không thiết kế trường hợp `compare(x, y)` báo lỗi nhưng `compare(y, x)` lại trả kết quả hợp lệ.

### 2.2. Thứ tự phải có tính bắc cầu

```text
c(x, y) > 0 và c(y, z) > 0  =>  c(x, z) > 0
```

Ví dụ, nếu điểm của `A` cao hơn `B`, điểm của `B` cao hơn `C`, thì quy tắc cùng chiều phải đặt `A` cao hơn `C`.

Không được tạo một vòng:

```text
0 đứng trước 1
1 đứng trước 2
2 đứng trước 0
```

Với vòng này, không tồn tại một dãy tuyến tính đáp ứng tất cả câu trả lời. Thuật toán không thể sửa một quan hệ tự mâu thuẫn thành thứ tự hợp lệ.

Điều kiện tương ứng ở chiều “đứng trước” cũng phải đúng; nó đi cùng điều kiện đổi dấu.

### 2.3. Những đối tượng cùng hạng phải ứng xử nhất quán với đối tượng thứ ba

```text
c(x, y) == 0  =>  sign(c(x, z)) == sign(c(y, z))
```

Nếu `x` và `y` cùng hạng, thay `x` bằng `y` khi so với cùng một `z` không được làm kết quả chuyển từ “trước” sang “sau”, hoặc từ “cùng hạng” sang “trước”.

Một phản ví dụ nhỏ:

| Phép so sánh | Kết quả được trả |
| --- | --- |
| `compare(0, 2)` | `0`: coi 0 và 2 cùng hạng |
| `compare(0, 1)` | Âm |
| `compare(2, 1)` | Dương |

Comparator đồng thời nói 0 và 2 cùng hạng, nhưng 1 lại nằm giữa chúng. Các câu trả lời không tương thích.

Quy tắc này mạnh hơn việc chỉ kiểm tra “hai đối tượng bằng điểm thì trả 0”. Các đối tượng được gom vào cùng một nhóm thứ tự phải được nhìn nhận giống nhau khi so với mọi nhóm khác.

Các công thức chính thức, điều kiện ngoại lệ và quy định về `equals` nằm trong [hợp đồng Comparator.compare của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T)).

## 3. Hai nghĩa của “nhất quán” cần tách rõ

### 3.1. Nhất quán của nhóm cùng hạng

Đây là điều kiện bắt buộc vừa nêu: khi `compare(x, y) == 0`, hai đối tượng phải so với mọi đối tượng thứ ba theo cùng dấu.

Một comparator chỉ xếp mặt hàng theo `score` có thể hoàn toàn hợp lệ. Hai mặt hàng khác mã nhưng cùng điểm được xếp cùng hạng, miễn mọi lần so sánh đều tiếp tục dùng đúng điểm đó.

Tính hợp lệ này không phụ thuộc vào việc chúng là một hay hai đối tượng, cùng hay khác mã.

### 3.2. Nhất quán với equals của các đối tượng được so sánh

Điều kiện thường mong muốn là:

```text
(compare(x, y) == 0) == x.equals(y)
```

Trong biểu thức trên, dấu `==` ở giữa so sánh hai giá trị boolean. Nó yêu cầu:

- Nếu hai đối tượng bằng nhau theo `equals`, comparator cũng trả 0.
- Nếu comparator trả 0, hai đối tượng cũng bằng nhau theo `equals`.

Đây là điều kiện **được khuyến nghị nhưng không bắt buộc đối với mọi comparator**. Nếu cố ý khác `equals`, phải hiểu và mô tả điều đó, đặc biệt khi comparator được đưa vào cây tập hợp hoặc cây ánh xạ.

Ví dụ với kiểu:

```java
record Item(String code, int score) {}
```

Hai đối tượng `new Item("A", 90)` và `new Item("B", 90)` không bằng nhau theo `equals` do `code` khác nhau. Comparator chỉ dùng `score` vẫn trả 0.

Comparator này không nhất quán với `equals` của record, nhưng không vì thế mà vi phạm ba ràng buộc về thứ tự. Nó đang xếp theo điểm, không định nghĩa định danh đầy đủ của mặt hàng.

Ngay cả comparator trả 0 cho mọi cặp trong một miền không rỗng cũng có thể đáp ứng các ràng buộc thứ tự: nó gom toàn bộ miền vào một hạng. Nó có hữu ích và phù hợp nơi sử dụng hay không là câu hỏi khác.

### 3.3. Giữ quy tắc ổn định trong khi sử dụng

Còn một yêu cầu thực hành: với cùng dữ liệu có liên quan không đổi, comparator phải tiếp tục mô tả cùng quy tắc.

Tránh dùng ngẫu nhiên, trạng thái tăng dần sau mỗi lần gọi, giờ hiện tại hoặc cấu hình đang bị thay đổi trong quá trình sắp xếp. Cũng không để luồng khác sửa trường dùng làm khóa so sánh trong lúc thuật toán đang chạy.

Điều này không được hiểu là đối tượng không bao giờ được thay đổi. Vấn đề là các lời so sánh thuộc cùng một thao tác hoặc cấu trúc phải dựa trên dữ liệu và quy tắc phù hợp với nhau.

Một comparator không có field riêng vẫn có thể mất ổn định nếu nó đọc trạng thái biến đổi của các phần tử.

## 4. Ảnh hưởng đến List, TreeSet và TreeMap

### 4.1. Sắp xếp List giữ lại các phần tử cùng hạng

Một danh sách có thể chứa nhiều mặt hàng cùng điểm. Sắp xếp theo điểm không loại chúng khỏi danh sách.

`List.sort` bảo đảm sắp xếp ổn định: những phần tử comparator xem là cùng hạng giữ thứ tự tương đối trước đó. Tuy nhiên, “ổn định” ở đây nói về cách thuật toán xử lý các phần tử hòa nhau; nó không biến comparator sai thành đúng, cũng không làm comparator trở nên nhất quán với `equals`. Xem [API List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Nếu cần thứ tự hiển thị không phụ thuộc vào thứ tự đầu vào khi bằng điểm, hãy thêm tiêu chí phụ rõ ràng.

### 4.2. TreeSet xem compare bằng 0 là cùng phần tử theo thứ tự

Khi dùng comparator theo điểm, thêm mặt hàng mã `"A"` điểm 90 và mặt hàng mã `"B"` điểm 90 vào một `TreeSet` sẽ chỉ giữ một phần tử đại diện cho hạng điểm 90.

Điều đó không chứng minh cây bị lỗi. Cây đang dùng đúng quy tắc mà comparator cung cấp. Nếu mục tiêu là lưu mọi mặt hàng riêng biệt, chỉ dùng điểm làm toàn bộ quy tắc là lựa chọn không phù hợp.

Cũng có thể tạo chiều sai lệch ngược lại: hai đối tượng `equals` nhau nhưng comparator phân biệt chúng do dùng thêm dữ liệu không thuộc `equals`. Khi đó cây có thể giữ những đối tượng mà hợp đồng tập hợp thông thường xem là trùng.

Vì vậy, nếu cần hành vi tập hợp đúng theo `equals`, quan hệ cùng hạng của comparator phải phù hợp với `equals`. Xem [API TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### 4.3. TreeMap áp dụng cùng nguyên tắc cho khóa

Với `TreeMap`, điều quan trọng là comparator của **khóa**. Nếu hai khóa so sánh bằng 0, `put` cho khóa sau cập nhật ánh xạ tương ứng thay vì tạo một khóa riêng trong cây.

Tính duy nhất theo khóa của `TreeMap` do thứ tự quyết định. Không thể giữ mọi bản ghi có cùng khóa so sánh bằng cách ép comparator trả một kết quả tùy ý khác 0; cách đó có thể phá hợp đồng. Hãy chọn mô hình khóa hoặc cấu trúc lưu trữ phù hợp. Xem [API TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

### 4.4. BigDecimal là ví dụ khác biệt có chủ đích

`new BigDecimal("2.0")` và `new BigDecimal("2.00")` có cùng giá trị số khi so sánh bằng `compareTo`, nhưng không bằng nhau theo `equals`, vì `equals` xét cả scale.

Bởi vậy, `HashSet` chứa hai giá trị này có thể có kích thước 2, trong khi `TreeSet` theo thứ tự tự nhiên có kích thước 1. Đây là khác biệt giữa hai hợp đồng tương đương được dùng, không phải lý do để kết luận thứ tự tự nhiên của `BigDecimal` vi phạm tính bắc cầu. Xem [API BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

## 5. Viết comparator an toàn và rõ ý định

### 5.1. Không so sánh số nguyên bằng phép trừ

Mẫu dễ sai:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Nếu `a` là `Integer.MIN_VALUE`, `b` là 0, phép trừ ở hai chiều đều cho một số âm do tràn miền `int`. Quan hệ đổi dấu bị phá.

`Integer.signum(a - b)` cũng không cứu được vì phép trừ đã tràn trước khi tính dấu. Tương tự, trừ hai `long` rồi ép về `int` không phải giải pháp.

Dùng:

```java
Comparator<Integer> safe = Integer::compare;
Comparator<Item> byScore = Comparator.comparingInt(Item::score);
```

Với trường `long` hoặc `double`, chọn API tương ứng như `comparingLong` hoặc `comparingDouble`. Không ép chênh lệch `double` về `int`: hai số khác nhau có thể bị quy về 0, và các giá trị đặc biệt cần quy tắc rõ ràng.

Quy tắc trả dấu của `Integer.compare` được công bố trong [API Integer.compare](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#compare(int,int)).

### 5.2. Khi hai đối tượng cùng hạng, phải trả 0

Mẫu sau sai:

```java
Comparator<Integer> bad = (a, b) -> a > b ? 1 : -1;
```

Khi `a` bằng `b`, nó vẫn trả âm. Chính một phần tử so với nó cũng không trả 0.

Không “sửa” việc `TreeSet` gộp phần tử bằng cách cố tình trả 1 hoặc -1 cho những đối tượng cùng hạng. Nếu phải giữ nhiều bản ghi, dùng danh sách hoặc thiết kế thêm tiêu chí phụ có ý nghĩa.

### 5.3. Ghép tiêu chí phụ theo thứ tự ưu tiên

Các khai báo minh họa sau dùng kiểu `Item` ở trên:

```java
Comparator<Item> byScore = Comparator.comparingInt(Item::score);

Comparator<Item> byScoreThenCode =
        byScore.thenComparing(Item::code);

Comparator<Item> scoreDescendingCodeAscending =
        byScore.reversed().thenComparing(Item::code);
```

`thenComparing` chỉ dùng tiêu chí sau khi tiêu chí trước trả 0. Nó không cộng điểm số của các phép so sánh.

Ở comparator cuối:

1. Điểm lớn đứng trước.
2. Khi bằng điểm, mã nhỏ theo thứ tự của `String` đứng trước.

Vị trí gọi `reversed()` thay đổi ý nghĩa:

```java
// Đảo toàn bộ quy tắc: điểm giảm và mã cũng giảm khi hòa điểm.
Comparator<Item> bothDescending =
        byScore.thenComparing(Item::code).reversed();
```

Trong record `Item` của ví dụ, so sánh đủ `score` và `code` giúp quan hệ bằng 0 phù hợp với `equals`, với giả định mã không null. Không suy rộng rằng cứ thêm một `thenComparing` bất kỳ là luôn nhất quán với `equals`; phải đối chiếu toàn bộ trường và quy tắc equality của kiểu đang dùng.

Để đảo một comparator có sẵn, dùng `reversed()` hoặc so hai đối số theo chiều ngược. Tránh viết `-comparator.compare(a, b)`: một kết quả hợp lệ có thể là `Integer.MIN_VALUE`, mà đổi dấu vẫn âm do tràn số.

### 5.4. Xác định chính sách null

Nếu miền dữ liệu có `null`, hãy nói rõ nó đứng đâu:

```java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());
```

Comparator trên đặt chuỗi null sau các chuỗi khác, và hai null cùng hạng.

Cần phân biệt:

- **Cả phần tử là null:** bọc comparator của phần tử.
- **Một thuộc tính của phần tử là null:** cung cấp comparator xử lý null cho thuộc tính đó.

Ví dụ minh họa với thuộc tính `code` có thể null:

```java
Comparator<Item> nullableCode = Comparator.comparing(
        Item::code,
        Comparator.nullsLast(Comparator.naturalOrder()));

Comparator<Item> nullableItem = Comparator.nullsLast(nullableCode);
```

Khai báo đầu xử lý mã null, nhưng chưa xử lý cả `Item` null. Khai báo thứ hai bổ sung lớp xử lý đó.

Đảo toàn bộ comparator còn đảo vị trí null. Chẳng hạn, `nullLast.reversed()` sẽ đặt null lên trước. Nếu muốn giảm dần các giá trị thực nhưng vẫn giữ null ở cuối, đặt `nullsLast` bao ngoài comparator giảm dần.

## 6. Chương trình hoàn chỉnh để quan sát hành vi

Lưu vào **ComparatorContractDemo.java**. Các API được dùng tương thích Java 17 trở lên:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class ComparatorContractDemo {
    record Item(String code, int score) {}

    private static List<String> describe(Collection<Item> items) {
        return items.stream()
                .map(item -> item.code() + ":" + item.score())
                .toList();
    }

    public static void main(String[] args) {
        Comparator<Integer> subtraction = (a, b) -> a - b;
        Comparator<Integer> safe = Integer::compare;
        int min = Integer.MIN_VALUE;

        System.out.println("Subtraction signs: "
                + Integer.signum(subtraction.compare(min, 0)) + ", "
                + Integer.signum(subtraction.compare(0, min)));
        System.out.println("Integer.compare signs: "
                + Integer.signum(safe.compare(min, 0)) + ", "
                + Integer.signum(safe.compare(0, min)));

        Item b = new Item("B", 90);
        Item a = new Item("A", 90);
        Item c = new Item("C", 75);
        List<Item> input = List.of(b, a, c);

        Comparator<Item> byScore = Comparator.comparingInt(Item::score);
        Comparator<Item> byScoreThenCode =
                byScore.thenComparing(Item::code);

        List<Item> ascending = new ArrayList<>(input);
        ascending.sort(byScoreThenCode);
        System.out.println("Ascending: " + describe(ascending));

        List<Item> descending = new ArrayList<>(input);
        descending.sort(byScore.reversed().thenComparing(Item::code));
        System.out.println("Descending score: " + describe(descending));

        System.out.println("Score tie compare: " + byScore.compare(a, b));
        System.out.println("Record equals: " + a.equals(b));

        TreeSet<Item> scoreOnly = new TreeSet<>(byScore);
        scoreOnly.addAll(input);
        System.out.println("TreeSet score only size: " + scoreOnly.size());

        TreeSet<Item> complete = new TreeSet<>(byScoreThenCode);
        complete.addAll(input);
        System.out.println("TreeSet score/code: " + describe(complete));

        List<String> names =
                new ArrayList<>(Arrays.asList("b", null, "a"));
        names.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("Nulls last: " + names);

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("Decimal compare: " + x.compareTo(y));
        System.out.println("Decimal equals: " + x.equals(y));
        System.out.println("HashSet decimals: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet decimals: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparatorContractDemo.java
java ComparatorContractDemo
```

Stdout:

```text
Subtraction signs: -1, -1
Integer.compare signs: -1, 1
Ascending: [C:75, A:90, B:90]
Descending score: [A:90, B:90, C:75]
Score tie compare: 0
Record equals: false
TreeSet score only size: 2
TreeSet score/code: [C:75, A:90, B:90]
Nulls last: [a, b, null]
Decimal compare: 0
Decimal equals: false
HashSet decimals: 2
TreeSet decimals: 1
```

### Đọc kết quả

**Hai dòng đầu** cho thấy comparator dùng phép trừ không giữ dấu đối nhau, còn `Integer.compare` giữ được.

**Hai danh sách đã sắp xếp** cho thấy tiêu chí điểm và mã hoạt động theo đúng thứ tự ưu tiên. Các mặt hàng bằng điểm không mất khỏi danh sách.

**`Score tie compare: 0` nhưng `Record equals: false`** là sự khác biệt có chủ đích của comparator chỉ dùng điểm.

**`TreeSet score only size: 2`** là kết quả của ba mặt hàng thuộc hai hạng điểm. Khi so tiếp mã, cây giữ đủ ba mặt hàng trong thứ tự mong muốn.

**Danh sách tên** chứng minh vị trí null được đặt cuối bằng comparator có hỗ trợ.

**Bốn dòng về BigDecimal** cho thấy một thứ tự hợp lệ có thể khác `equals`, và sự khác biệt đó làm hai cấu trúc tập hợp nhận diện trùng lặp khác nhau.

## 7. Kiểm tra hợp đồng bằng cặp và bộ ba

Chỉ đưa một danh sách vào `sort` rồi nhìn thấy kết quả có vẻ đúng là kiểm tra chưa đủ. Thuật toán có thể không thực hiện đúng những phép so sánh làm lộ lỗi trên bộ dữ liệu nhỏ đó.

Chương trình dưới kiểm tra các ràng buộc trên **một mẫu hữu hạn**. Mẫu phải nằm trong miền mà comparator có thể so sánh bình thường; chương trình không đóng vai trò bộ kiểm thử đầy đủ cho chính sách ngoại lệ.

Lưu vào **ComparatorCheckDemo.java**:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorCheckDemo {
    static <T> String firstViolation(
            Comparator<? super T> comparator, List<T> sample) {
        for (T x : sample) {
            if (comparator.compare(x, x) != 0) {
                return "self comparison";
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                int xy = Integer.signum(comparator.compare(x, y));
                int yx = Integer.signum(comparator.compare(y, x));
                if (xy != -yx) {
                    return "opposite signs";
                }
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                for (T z : sample) {
                    int xy = comparator.compare(x, y);
                    int xz = comparator.compare(x, z);
                    int yz = comparator.compare(y, z);

                    if (xy == 0
                            && Integer.signum(xz) != Integer.signum(yz)) {
                        return "zero consistency";
                    }
                }
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                for (T z : sample) {
                    if (comparator.compare(x, y) > 0
                            && comparator.compare(y, z) > 0
                            && comparator.compare(x, z) <= 0) {
                        return "transitivity";
                    }
                }
            }
        }
        return "no violation in sample";
    }

    public static void main(String[] args) {
        Comparator<Integer> subtract = (a, b) -> a - b;

        Comparator<Integer> cyclic = (a, b) -> {
            if (a.equals(b)) {
                return 0;
            }
            if ((a == 0 && b == 1)
                    || (a == 1 && b == 2)
                    || (a == 2 && b == 0)) {
                return -1;
            }
            return 1;
        };

        Comparator<Integer> brokenZero = (a, b) -> {
            if ((a == 0 && b == 2) || (a == 2 && b == 0)) {
                return 0;
            }
            return Integer.compare(a, b);
        };

        System.out.println("Safe: " + firstViolation(
                Integer::compare,
                List.of(Integer.MIN_VALUE, -1, 0, 1, Integer.MAX_VALUE)));
        System.out.println("Subtract: " + firstViolation(
                subtract, List.of(Integer.MIN_VALUE, 0)));
        System.out.println("Cyclic: " + firstViolation(
                cyclic, List.of(0, 1, 2)));
        System.out.println("Broken zero: " + firstViolation(
                brokenZero, List.of(0, 1, 2)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparatorCheckDemo.java
java ComparatorCheckDemo
```

Stdout:

```text
Safe: no violation in sample
Subtract: opposite signs
Cyclic: transitivity
Broken zero: zero consistency
```

### 7.1. Ý nghĩa của các comparator thử nghiệm

- `Integer::compare` không bị phát hiện vi phạm trên mẫu chứa cả giá trị biên.
- `subtract` làm lộ lỗi dấu do tràn số.
- `cyclic` định nghĩa vòng 0 trước 1, 1 trước 2, 2 trước 0. Nó tự so sánh đúng và đổi dấu đúng, nhưng vi phạm bắc cầu.
- `brokenZero` coi 0 và 2 cùng hạng, trong khi vẫn đặt 1 ở giữa. Bộ kiểm tra phát hiện điều kiện nhất quán của hạng 0 bị phá.

Một comparator có thể vi phạm nhiều điều kiện cùng lúc. Hàm trả về điều kiện đầu tiên tìm được theo thứ tự kiểm tra, không khẳng định đó là lỗi duy nhất.

### 7.2. Những giới hạn phải hiểu

Các vòng lặp ba lớp có chi phí bậc ba theo số phần tử mẫu. Chúng phù hợp mẫu nhỏ để minh họa hoặc kiểm thử, không dùng để kiểm tra toàn bộ dữ liệu lớn trong luồng xử lý chính.

Không tìm thấy vi phạm trong mẫu **không phải chứng minh đúng với mọi đầu vào**. Cần bổ sung:

- Số âm, số dương, 0 và biên của kiểu số.
- Hai đối tượng khác nhau nhưng `equals` nhau.
- Hai đối tượng cùng tiêu chí chính nhưng khác tiêu chí phụ.
- Null nếu được chấp nhận, và cả hai chiều so sánh nếu null bị từ chối.
- Bộ ba có khả năng tạo vòng hoặc làm lộ nhóm cùng hạng không nhất quán.
- Dữ liệu sinh ngẫu nhiên có thể tái lập để mở rộng phạm vi kiểm thử.

Nếu thiết kế yêu cầu nhất quán với `equals`, kiểm tra thêm điều kiện đó riêng. Không đưa nó vào nhóm lỗi bắt buộc rồi kết luận mọi comparator chỉ xếp theo một thuộc tính đều sai.

Nếu comparator dùng dữ liệu từ bên ngoài, còn phải kiểm tra việc cấu hình hoặc dữ liệu có bị thay đổi trong lúc sử dụng không. Ba vòng lặp không thể tự chứng minh tính ổn định của toàn bộ hệ thống.

## 8. Khi comparator sai hoặc khóa so sánh bị thay đổi

Thuật toán sắp xếp có thể ném `IllegalArgumentException` khi phát hiện vi phạm hợp đồng. Tài liệu `Arrays.sort` cho phép cơ chế phát hiện như vậy, nhưng không bảo đảm mọi comparator sai đều được phát hiện ở mọi lần chạy. Do đó, “không có ngoại lệ” không chứng minh comparator đúng. Xem [API Arrays.sort với Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#sort(T%5B%5D,java.util.Comparator)).

Tương tự, không thay trường dùng làm khóa so sánh của phần tử đang nằm trong `TreeSet` hoặc khóa đang nằm trong `TreeMap`. Vị trí đã tổ chức theo giá trị cũ không tự được xây lại khi field thay đổi; tra cứu có thể không còn theo đường mong muốn.

Nếu cần đổi dữ liệu quyết định vị trí, lựa chọn thường gặp là:

1. Xóa phần tử hoặc ánh xạ khi khóa so sánh còn ở trạng thái cũ.
2. Thay đổi dữ liệu.
3. Thêm lại theo thứ tự mới.

Thiết kế đối tượng khóa không cho sửa các trường quyết định equality và thứ tự thường dễ kiểm soát hơn. Với cập nhật đồng thời, toàn bộ quy trình còn cần cơ chế phối hợp phù hợp; comparator không cung cấp đồng bộ cho collection.

## 9. Danh sách tự rà soát

Trước khi đưa comparator vào mã sử dụng, hãy trả lời:

1. Miền đầu vào gồm những kiểu và những giá trị nào? Null có thuộc miền không?
2. Kết quả âm, 0 và dương thể hiện đúng quy tắc nghiệp vụ nào?
3. Đổi chiều có đổi dấu, và tự so sánh có trả 0 không?
4. Có bộ ba nào tạo vòng thứ tự không?
5. Các đối tượng cùng hạng có so với mọi đối tượng thứ ba theo cùng dấu không?
6. Quan hệ bằng 0 có phù hợp với `equals` không? Nếu không, nơi sử dụng có chấp nhận không?
7. Có phép trừ, ép kiểu, dữ liệu biến đổi hoặc ngoại lệ một chiều làm hỏng quy tắc không?
8. Danh sách cần giữ những phần tử hòa nhau hay một tập/map cần nhận diện chúng là cùng khóa?
9. Tiêu chí phụ, chiều giảm dần và vị trí null đã được kiểm chứng cùng nhau chưa?

Hợp đồng comparator là nền tảng để thuật toán và cấu trúc có thứ tự dựa vào cùng một quan hệ. Viết rõ quan hệ trước, ghép các phép so sánh an toàn, rồi kiểm chứng bằng cặp và bộ ba sẽ giúp giải thích được kết quả thay vì chỉ hy vọng một lần sắp xếp chạy qua.
