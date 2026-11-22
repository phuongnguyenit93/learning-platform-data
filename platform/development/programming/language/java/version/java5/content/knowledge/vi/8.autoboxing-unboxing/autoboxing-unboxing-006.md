# Bộ nhớ đệm lớp bao và giới hạn bảo đảm về định danh

## 1. Cùng giá trị không nhất thiết là cùng đối tượng

Hai tham chiếu `Integer` có thể biểu diễn cùng số nhưng không nhất thiết trỏ tới cùng một đối tượng. Ngược lại, các thao tác boxing hoặc gọi factory có thể dùng lại một đối tượng đã có trong **bộ nhớ đệm (cache)**.

```java
Integer first = 42;
Integer second = 42;
boolean sameReference = first == second;
boolean sameValue = first.equals(second);
```

Trong ví dụ hằng số nhỏ này, cả hai kết quả đều là `true`, nhưng vì hai lý do khác nhau:

- `==` giữa hai tham chiếu `Integer` kiểm tra **định danh đối tượng**: chúng có phải cùng đối tượng không?
- `equals` của `Integer` kiểm tra **giá trị**: đối số có phải `Integer` mang cùng giá trị số không?

Cache giải thích vì sao một số phép so sánh tham chiếu tình cờ cũng giống so sánh số. Nó không biến `==` giữa hai wrapper thành toán tử bằng nhau về giá trị.

Bài này chỉ dùng kiến thức và API còn áp dụng trong Java hiện hành. Ví dụ chạy với Java 17 trở lên và không dùng constructor wrapper đã bị deprecated để ép tạo đối tượng riêng.

## 2. Vì sao wrapper có thể được dùng chung?

Các wrapper như `Integer` và `Long` không cho sửa giá trị được chứa trong một đối tượng sau khi tạo. Vì thế, nhiều nơi có thể dùng chung một đối tượng biểu diễn một giá trị mà không có thao tác “đổi số ở bên trong” làm ảnh hưởng tới nhau.

Một cách hình dung cache:

```text
tham chiếu a ──┐
              ├──> Integer biểu diễn 42
tham chiếu b ──┘
```

Dùng lại đối tượng có thể giảm việc tạo wrapper cho các giá trị thường gặp. Nhưng không được từ đó suy ra rằng mọi lần boxing đều tránh cấp phát, hoặc mọi số ngoài một vùng nhỏ đều chắc chắn tạo đối tượng mới. Đó là những khẳng định cần hợp đồng cụ thể hoặc bằng chứng về implementation và tối ưu hóa khi chạy.

Biến tham chiếu vẫn có thể được gán sang đối tượng khác. Ví dụ, `Integer x = 42; x++;` không sửa đối tượng trong cache thành `43`; phép toán lấy giá trị số, tăng và gán lại một tham chiếu kết quả.

## 3. Bảo đảm của ngôn ngữ khi boxing hằng số

Theo quy tắc boxing trong đặc tả Java, khi giá trị được boxing là kết quả của một **biểu thức hằng** thuộc các kiểu được nêu và nằm trong vùng tương ứng, các lần boxing của cùng giá trị phải có cùng tham chiếu.

| Kiểu primitive của giá trị hằng được boxing | Vùng giá trị được bảo đảm định danh |
| --- | --- |
| `boolean` | `true`, `false` |
| `byte` | Toàn bộ miền giá trị `byte`, tức -128 đến 127 |
| `short` | -128 đến 127 |
| `int` | -128 đến 127 |
| `long` | -128 đến 127 |
| `char` | U+0000 đến U+007F, tức giá trị 0 đến 127 |

Các đầu mút đều được tính trong vùng. Quy tắc này không có một bảo đảm tương tự cho boxing `float` và `double`.

Ví dụ với biểu thức hằng:

```java
Integer a = 100;
Integer b = 100;
Long c = 100L;
Long d = 100L;
Character e = 'A';
Character f = 'A';

System.out.println(a == b); // true
System.out.println(c == d); // true
System.out.println(e == f); // true
```

Một biến hằng nguyên thủy cũng có thể tham gia biểu thức hằng:

```java
final int SMALL = 100;
Integer first = SMALL;
Integer second = SMALL;
System.out.println(first == second); // true
```

Không phải mọi biến `final` đều là biến hằng theo nghĩa này. Một giá trị lấy từ đầu vào lúc chạy không trở thành biểu thức hằng chỉ vì biến sau đó không được gán lại.

Điểm cần giữ chính xác là **điều kiện biểu thức hằng** của bảo đảm ngôn ngữ. Không rút gọn thành khẳng định rằng ngôn ngữ luôn bảo đảm định danh cho mọi cách sản sinh một giá trị nhỏ trong mọi chương trình. Các API factory có thể đưa ra bảo đảm riêng rộng hơn cho những lời gọi cụ thể, như mục tiếp theo.

## 4. Bảo đảm riêng của valueOf với đối số primitive

Hợp đồng của một số phương thức factory nói rõ việc dùng cache, không yêu cầu đối số truyền vào phải là biểu thức hằng.

| Phương thức | Phần bảo đảm của hợp đồng API |
| --- | --- |
| `Boolean.valueOf(boolean)` | Trả `Boolean.TRUE` hoặc `Boolean.FALSE` tương ứng |
| `Byte.valueOf(byte)` | Cache toàn bộ miền giá trị `byte` |
| `Short.valueOf(short)` | Luôn cache -128 đến 127; có thể cache thêm |
| `Integer.valueOf(int)` | Luôn cache -128 đến 127; có thể cache thêm |
| `Long.valueOf(long)` | Luôn cache -128 đến 127; có thể cache thêm |
| `Character.valueOf(char)` | Luôn cache 0 đến 127; có thể cache thêm |

Ví dụ:

```java
int input = Integer.parseInt("100");
Integer first = Integer.valueOf(input);
Integer second = Integer.valueOf(input);
System.out.println(first == second); // true theo hợp đồng valueOf(int).
```

`input` không phải biểu thức hằng, nhưng lời gọi ở đây nêu rõ `Integer.valueOf(int)` và giá trị nằm trong vùng mà API cam kết cache. Không cần dựa vào suy đoán về cách compiler hạ boxing thành bytecode.

Cũng cần đọc đúng overload: bảng nói về các factory nhận primitive như `valueOf(int)`, không phải một quy tắc tự động áp cho mọi phương thức có tên `valueOf`, `parse`, `decode` hoặc mọi đường tạo wrapper khác. Muốn kết luận về một đường đi cụ thể, đọc hợp đồng của chính đường đi đó.

`Integer.parseInt` trả về primitive `int`, không phải một đối tượng `Integer` được lấy từ cache. Ở ví dụ, bước tạo/lấy wrapper diễn ra trong `Integer.valueOf` sau bước parse.

## 5. Ngoài vùng bảo đảm: không được khẳng định luôn khác nhau

```java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);
boolean identityObserved = left == right;
boolean equalValue = left.equals(right);
```

`equalValue` là `true`. Còn kết quả định danh nằm ngoài vùng bắt buộc cache của `Integer.valueOf(int)`: một implementation có thể dùng lại đối tượng, cũng có thể không dùng lại.

Vì vậy, cả hai phát biểu sau đều không phải quy tắc portable:

- “Mọi số ngoài -128 đến 127 đều làm `==` trả về `false`.”
- “Máy của tôi cho `true` với 1000, nên mọi môi trường cũng phải như vậy.”

Một cache mở rộng, cấu hình hoặc implementation khác có thể làm một thí nghiệm định danh cho kết quả khác mà vẫn tuân thủ hợp đồng. Không đưa giới hạn mở rộng quan sát được vào logic nghiệp vụ.

Tương tự, việc không có bảo đảm cache cho `Float` hoặc `Double` không phải một lời hứa rằng mọi factory của chúng luôn tạo một định danh mới. Thiếu bảo đảm dùng chung không đồng nghĩa với bảo đảm khác nhau.

## 6. Định danh và giá trị phải được kiểm tra bằng đúng phép toán

### Hai wrapper: == là định danh

```java
Integer a = Integer.valueOf(500);
Integer b = Integer.valueOf(500);
boolean sameObject = a == b;
boolean sameNumber = java.util.Objects.equals(a, b);
```

`Objects.equals` xử lý được cả trường hợp tham chiếu `null`, nhưng nó vẫn dùng quan hệ `equals` của các đối tượng. Nó không tự chuẩn hóa `Integer` và `Long` thành một kiểu số chung.

Ví dụ `Objects.equals(Integer.valueOf(5), Long.valueOf(5L))` là `false` vì hai wrapper khác lớp. Nếu nghiệp vụ cần so sánh số giữa các kiểu khác nhau, chọn phép chuyển đổi số rõ ràng, phù hợp với độ chính xác cần giữ.

### Wrapper với primitive: có thể là unboxing

```java
Integer boxed = Integer.valueOf(1000);
boolean sameNumericValue = boxed == 1000; // true.
```

Bên phải là `int`, nên biểu thức unbox bên trái để so sánh số. Kết quả này không phải bằng chứng rằng `1000` được cache. Nếu `boxed` là `null`, phép so sánh ấy gây `NullPointerException`.

### Gán cùng một tham chiếu: không liên quan tới cache

```java
Integer original = Integer.valueOf(1000);
Integer alias = original;
System.out.println(original == alias); // true.
```

Hai biến giữ cùng tham chiếu do phép gán. Không có hai lời gọi factory độc lập để kiểm tra chuyện dùng chung đối tượng. Mọi giá trị đều có thể tạo tình huống alias như vậy, kể cả ngoài vùng cache bắt buộc.

## 7. Chương trình chạy đầy đủ với stdout có thể dựa vào hợp đồng

Lưu thành **`WrapperIdentityGuaranteesDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class WrapperIdentityGuaranteesDemo {
    public static void main(String[] args) {
        Integer literalA = 42;
        Integer literalB = 42;
        System.out.println("literal identity=" + (literalA == literalB));

        int input = Integer.parseInt("42");
        Integer factoryA = Integer.valueOf(input);
        Integer factoryB = Integer.valueOf(input);
        System.out.println("factory identity=" + (factoryA == factoryB));

        Long longA = Long.valueOf(127L);
        Long longB = Long.valueOf(127L);
        System.out.println("long identity=" + (longA == longB));

        Character charA = Character.valueOf('A');
        Character charB = Character.valueOf('A');
        System.out.println("character identity=" + (charA == charB));

        Boolean truth = Boolean.valueOf(true);
        System.out.println("boolean singleton=" + (truth == Boolean.TRUE));

        Integer largeA = Integer.valueOf(1000);
        Integer largeB = Integer.valueOf(1000);
        System.out.println("large value equal=" + Objects.equals(largeA, largeB));
        System.out.println("large primitive equal=" + (largeA == 1000));

        Integer alias = largeA;
        System.out.println("alias identity=" + (largeA == alias));

        Map<Integer, String> labels = new HashMap<>();
        labels.put(1000, "ready");
        System.out.println("map lookup=" + labels.get(Integer.valueOf(1000)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all WrapperIdentityGuaranteesDemo.java
java WrapperIdentityGuaranteesDemo
```

Stdout chính xác:

```text
literal identity=true
factory identity=true
long identity=true
character identity=true
boolean singleton=true
large value equal=true
large primitive equal=true
alias identity=true
map lookup=ready
```

Các dòng định danh trong vùng bảo đảm dùng đúng điều kiện đã nêu. Với số 1000, chương trình kiểm tra giá trị, so sánh với primitive hoặc gán alias, nên không phụ thuộc việc cache có được mở rộng hay không.

`HashMap` dùng `equals` và `hashCode` theo hợp đồng của khóa, không dùng định danh đối tượng như tiêu chí bằng nhau của các khóa `Integer`. Việc tra khóa 1000 vì vậy không cần hai lần lấy wrapper phải trỏ tới cùng đối tượng.

Nếu muốn làm thí nghiệm riêng về môi trường, có thể in thêm `largeA == largeB`, nhưng kết quả đó cần được ghi rõ là **quan sát implementation của lần chạy**, không gắn một stdout cố định như thể được đặc tả bắt buộc.

## 8. Không dùng cache như một cơ chế định danh của ứng dụng

Các wrapper được tài liệu Java hiện hành xem là các lớp dựa trên giá trị (value-based classes). Hãy coi các thể hiện bằng nhau về giá trị là thay thế được cho nhau, thay vì thiết kế logic phụ thuộc vào việc chúng có dùng chung một định danh hay không.

Một số hệ quả thực tế:

- Không dùng `Integer` làm token “mỗi lần tạo phải khác nhau” để nhận diện một sự kiện hoặc yêu cầu.
- Không dùng wrapper làm monitor đồng bộ hóa. Các nơi không liên quan có thể dùng chung một đối tượng cache, và API hiện hành cũng không khuyến nghị dựa vào định danh của các lớp này cho đồng bộ hóa.
- Không dùng `System.identityHashCode` như một phép so sánh giá trị số hoặc như mã định danh nghiệp vụ duy nhất; nó không thay thế `equals`, và giá trị hash có thể trùng nhau.
- Không đổi sang cơ chế khóa dùng định danh đối tượng chỉ để phân biệt các wrapper đang bằng nhau về số nếu yêu cầu thật sự là nhóm theo giá trị.

Nếu cần khóa đồng bộ hóa riêng cho một đối tượng dịch vụ, tạo và sở hữu một đối tượng khóa chuyên biệt. Nếu cần định danh nghiệp vụ, mô hình hóa định danh ấy như dữ liệu, không dựa vào lựa chọn cache của wrapper.

Đây là giới hạn sử dụng của API hiện hành, không phải một mẹo để dự đoán địa chỉ bộ nhớ của đối tượng. Java không cung cấp cam kết rằng định danh quan sát được cho biết một đối tượng nằm ở địa chỉ cố định nào trong heap.

## 9. Cách phân loại một kết luận về ==

Khi gặp một câu hỏi “hai wrapper này có `==` nhau không?”, kiểm tra theo thứ tự:

1. Hai toán hạng đều là tham chiếu wrapper, hay một bên là primitive làm phát sinh unboxing?
2. Hai biến có được gán cùng một tham chiếu ngay từ đầu không? Nếu có, không cần viện đến cache.
3. Nếu là hai lần boxing độc lập, điều kiện biểu thức hằng và vùng bảo đảm của ngôn ngữ có được đáp ứng không?
4. Nếu là lời gọi factory, hợp đồng của đúng overload có cam kết dùng chung đối tượng cho giá trị ấy không?
5. Nếu không có bảo đảm, đánh dấu kết quả định danh là phụ thuộc implementation; dùng phép so sánh giá trị cho logic cần giá trị.

Kiểm tra ranh giới `127`/`128` hữu ích để thấy sự khác nhau giữa bảo đảm và quan sát, nhưng không phải một chứng minh rằng `128` luôn phải cho định danh khác nhau. Bài kiểm thử portable chỉ nên chốt những điều mà hợp đồng hoặc chính quan hệ alias bảo đảm.

## 10. Tự thực hành

1. Thay literal 42 trong chương trình thành 127 rồi -128. Giải thích vì sao hai đầu mút vẫn thuộc vùng bảo đảm.
2. Tạo hai lần `Integer.valueOf` với một giá trị nhận từ chuỗi đầu vào là 100. Xác định bảo đảm đang viện dẫn từ API nào, khác gì với điều kiện biểu thức hằng.
3. Thử in `Integer.valueOf(128) == Integer.valueOf(128)` và ghi lại môi trường chạy. Không viết một assertion bắt buộc `false` cho mọi JVM.
4. So sánh `Integer` 1000 với primitive 1000 và với một wrapper 1000 khác. Nêu cơ chế của từng biểu thức thay vì chỉ ghi kết quả quan sát.
5. Đặt một khóa `Integer` 1000 vào `HashMap` rồi tra bằng một giá trị `Integer` bằng nhau. Giải thích vì sao logic không cần cache mở rộng.

Cache của wrapper có thể làm nhiều tham chiếu dùng chung một đối tượng, nhưng quan hệ bằng nhau về giá trị vẫn là hợp đồng cần dùng cho dữ liệu số thông thường. Phân biệt bảo đảm ngôn ngữ, hợp đồng factory và quan sát implementation giúp tránh biến một tối ưu hóa thành giả định sai trong chương trình.

## Tài liệu đối chiếu

- [JLS §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): điều kiện biểu thức hằng và vùng bảo đảm định danh khi boxing.
- [Integer.valueOf(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#valueOf(int)), [Long.valueOf(long)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Long.html#valueOf(long)), [Short.valueOf(short)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Short.html#valueOf(short)): vùng cache bắt buộc của các factory số tương ứng.
- [Byte.valueOf(byte)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Byte.html#valueOf(byte)), [Character.valueOf(char)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#valueOf(char)), [Boolean.valueOf(boolean)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Boolean.html#valueOf(boolean)): hợp đồng factory cụ thể cho từng wrapper.
- [Value-based Classes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/ValueBased.html): giới hạn của các thao tác nhạy cảm với định danh.
