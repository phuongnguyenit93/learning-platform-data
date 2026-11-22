# Thực hành: Xây dựng đối tượng tọa độ bất biến với equals(), hashCode() và toString()

## 1. Mục tiêu và yêu cầu

Bài thực hành xây dựng kiểu dữ liệu **tọa độ hai chiều** `Point2D` bằng Java 17+. Mỗi đối tượng biểu diễn một điểm có hai tọa độ nguyên `x` và `y`. Hai đối tượng độc lập phải được xem là **bằng nhau về giá trị** khi cả `x` lẫn `y` bằng nhau; các đối tượng này phải hoạt động đúng khi được dùng làm phần tử trong `HashSet` hoặc làm khóa trong `HashMap`.

Hoàn thành bài này, bạn cần hiểu và tự triển khai được:

1. **Tính bất biến (immutability):** sau khi được khởi tạo, trạng thái tọa độ của một `Point2D` không thể thay đổi.
2. **`equals(Object)`:** định nghĩa đúng thế nào là hai tọa độ bằng nhau; tuân thủ các tính chất phản xạ, đối xứng, bắc cầu, nhất quán và không bằng `null`.
3. **`hashCode()`:** các đối tượng bằng nhau phải có cùng mã băm; mã băm không phải định danh duy nhất.
4. **`toString()`:** xuất biểu diễn dễ đọc, ổn định và hữu ích khi ghi log/debug.
5. **Sử dụng thực tế:** tạo đối tượng bằng nhau từ các lần `new` khác nhau, đưa vào `HashSet`/`HashMap` và lý giải kết quả.

**Đặc tả:** tọa độ được biểu diễn bằng kiểu nguyên `int`; cho phép số âm, `0` và toàn bộ miền `int`. Bài tập chỉ xét **tọa độ 2D**, không thêm độ dài, vận tốc, màu sắc hay trạng thái phụ vào khái niệm bằng nhau.

## 2. Thiết kế lớp bất biến trước khi viết code

Một thiết kế tối giản nhưng đúng có các quyết định sau:

| Thành phần | Thiết kế | Vì sao |
| --- | --- | --- |
| Khai báo lớp | `public final class Point2D` | Không cho subclass thay ngữ nghĩa `equals()` hoặc mở rộng trạng thái theo cách gây bất ngờ. |
| Thuộc tính | `private final int x` và `private final int y` | Đóng gói, gán một lần; `int` là kiểu nguyên thủy nên không có trạng thái bên trong để ai khác sửa. |
| Constructor | Nhận `x` và `y`, gán vào hai trường | Thiết lập trạng thái đầy đủ từ lúc tạo. |
| API đọc | `x()` và `y()` | Chỉ trả về bản sao giá trị nguyên thủy; không có setter. |
| `equals(Object)` | So sánh cả `x` và `y`, sau khi kiểm tra kiểu | Bằng nhau theo nội dung tọa độ, không phụ thuộc cùng tham chiếu. |
| `hashCode()` | Kết hợp mã băm hai tọa độ theo phép tính cố định | Tương thích với `equals()`; kết quả không thay đổi theo thời gian. |
| `toString()` | `Point2D{x=3, y=7}` | Giúp nhận dạng trạng thái khi in/log. |

Không có `setX()`, `setY()` hay phương thức nào gán lại hai trường. Đặc tính bất biến là điều kiện then chốt giúp một `Point2D` giữ được mã băm ổn định khi nó đã được đưa vào collection dựa trên hash.

**Phân biệt:** `private` che chi tiết cài đặt; `final` trên trường ngăn gán lại trường sau khởi tạo; `final` trên lớp ngăn kế thừa. Riêng `final` không tự tạo bất biến sâu nếu trường tham chiếu tới `List`, mảng hoặc đối tượng có thể sửa. Ví dụ này dùng hai `int` nên không phát sinh bài toán sao chép phòng vệ (defensive copy).

## 3. Cài đặt đầy đủ Point2D.java

Tạo file tên chính xác là `Point2D.java`:

```java
public final class Point2D {
    private final int x;
    private final int y;

    public Point2D(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Point2D other)) {
            return false;
        }
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        int result = Integer.hashCode(x);
        result = 31 * result + Integer.hashCode(y);
        return result;
    }

    @Override
    public String toString() {
        return "Point2D{x=" + x + ", y=" + y + "}";
    }
}
```

Đây là **một lớp Java độc lập biên dịch được**: file và tên lớp `public` trùng nhau. `instanceof Point2D other` là cú pháp pattern matching được hỗ trợ trong Java 17; nếu đối tượng kiểm tra là `null` hoặc không phải `Point2D`, nhánh điều kiện trả về `false` mà không ném `ClassCastException`.

### Vì sao equals(Object) không nhận Point2D làm tham số?

`Object` quy định chữ ký `public boolean equals(Object obj)`. Nếu bạn chỉ viết `public boolean equals(Point2D other)`, đó là **overload**, không override `Object.equals(Object)`. Các collection dùng `equals(Object)` sẽ tiếp tục nhận phép so sánh tham chiếu kế thừa từ `Object`, làm mất mục đích so sánh tọa độ. `@Override` giúp trình biên dịch phát hiện khi chữ ký không thật sự ghi đè phương thức của lớp cha.

### Giải thích từng nhánh equals

- `this == obj`: chính cùng đối tượng thì chắc chắn bằng nhau; đây là tối ưu an toàn, không thay thế việc so sánh giá trị giữa hai instance khác nhau.
- `!(obj instanceof Point2D other)`: trả `false` khi `obj` là `null` hoặc thuộc kiểu khác; sau điều kiện, biến `other` có kiểu `Point2D`.
- `x == other.x && y == other.y`: **cả hai** tọa độ phải giống nhau. Do `x`/`y` đều là `int`, toán tử `==` kiểm tra đúng **giá trị nguyên thủy**; nếu trường là tham chiếu tới một kiểu dữ liệu cần bằng nhau theo giá trị, phải cân nhắc `equals()` tương ứng.
- Vì lớp `Point2D` là `final`, ta không có subclass nào cần quyết định so sánh thêm hoặc bớt trạng thái; cách kiểm tra `instanceof` phù hợp với thiết kế này.

### Giải thích hashCode

Với hai tọa độ `int`, `Integer.hashCode(value)` trả về chính giá trị `int` đó. Công thức trên tương đương về kết quả với:

```java
return 31 * x + y;
```

Việc dùng hệ số `31` là một cách kết hợp trường phổ biến. Nó **không bắt buộc mã băm của mọi tọa độ phải khác nhau**. Chẳng hạn `Point2D(0, 31)` và `Point2D(1, 0)` cùng có `hashCode() == 31`, nhưng `equals() == false`.

Khi phép tính `int` vượt miền số nguyên 32 bit, Java áp dụng phép toán số nguyên với kết quả tràn theo quy tắc ngôn ngữ; hai đối tượng có cùng `x` và `y` vẫn nhận cùng một mã băm. Không cần xử lý ngoại lệ cho phép cộng hoặc nhân `int` ở đây.

Có thể sử dụng `Objects.hash(x, y)` cho tính tiện lợi, nhưng kết quả số học sẽ **khác** công thức đang dùng vì thuật toán gộp của `Objects.hash`; đồng thời lời gọi varargs có thể phát sinh chi phí boxing/array. Hãy chọn một cách nhất quán, không thay đổi mã băm trong khi phụ thuộc vào giá trị cũ được lưu/persist ở nơi khác. Với bài tập này, công thức tường minh dễ hiểu và không tạo bộ nhớ phụ.

### Giải thích toString

`toString()` trả về chuỗi nêu **đúng tên kiểu và cả hai tọa độ** theo định dạng do ta tự chọn. Mục tiêu là thông tin phục vụ người đọc và debug, **không phải** định dạng dữ liệu trao đổi được bảo đảm để parse. Không đưa địa chỉ bộ nhớ, identity hash code hay mã bí mật vào `toString()`. Trong bài này, hai tọa độ nguyên là thông tin công khai, an toàn để hiển thị.

## 4. Chương trình demo chạy được (CoordinateDemo.java)

Tạo file `CoordinateDemo.java` trong **cùng thư mục** với `Point2D.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CoordinateDemo {
    public static void main(String[] args) {
        Point2D p = new Point2D(3, 7);
        Point2D sameCoordinates = new Point2D(3, 7);
        Point2D third = new Point2D(3, 7);
        Point2D otherCoordinates = new Point2D(3, 8);

        System.out.println("p = " + p);
        System.out.println("p == sameCoordinates: " + (p == sameCoordinates));
        System.out.println("p.equals(sameCoordinates): "
                + p.equals(sameCoordinates));
        System.out.println("p.equals(otherCoordinates): "
                + p.equals(otherCoordinates));
        System.out.println("p.equals(null): " + p.equals(null));
        System.out.println("p.equals(text): " + p.equals("3,7"));
        System.out.println("symmetric equality: "
                + (p.equals(sameCoordinates) == sameCoordinates.equals(p)));
        System.out.println("transitive equality: "
                + (p.equals(sameCoordinates)
                   && sameCoordinates.equals(third)
                   && p.equals(third)));
        System.out.println("hash(p): " + p.hashCode());
        System.out.println("hash(sameCoordinates): "
                + sameCoordinates.hashCode());

        Set<Point2D> set = new HashSet<>();
        System.out.println("set.add(p): " + set.add(p));
        System.out.println("set.add(sameCoordinates): "
                + set.add(sameCoordinates));
        System.out.println("set.add(otherCoordinates): "
                + set.add(otherCoordinates));
        System.out.println("set.size(): " + set.size());

        Map<Point2D, String> labels = new HashMap<>();
        labels.put(p, "checkpoint");
        System.out.println("lookup by equal key: "
                + labels.get(sameCoordinates));

        Point2D collisionA = new Point2D(0, 31);
        Point2D collisionB = new Point2D(1, 0);
        System.out.println("collision equal hashes: "
                + (collisionA.hashCode() == collisionB.hashCode()));
        System.out.println("collision equals: "
                + collisionA.equals(collisionB));

        Set<Point2D> collisionSet = new HashSet<>();
        collisionSet.add(collisionA);
        collisionSet.add(collisionB);
        System.out.println("collision set size: " + collisionSet.size());
    }
}
```

Từ thư mục chứa cả hai file, chạy bằng JDK 17 trở lên:

```bash
javac Point2D.java CoordinateDemo.java
java CoordinateDemo
```

Output dự kiến, không phụ thuộc thứ tự duyệt `HashSet`:

```text
p = Point2D{x=3, y=7}
p == sameCoordinates: false
p.equals(sameCoordinates): true
p.equals(otherCoordinates): false
p.equals(null): false
p.equals(text): false
symmetric equality: true
transitive equality: true
hash(p): 100
hash(sameCoordinates): 100
set.add(p): true
set.add(sameCoordinates): false
set.add(otherCoordinates): true
set.size(): 2
lookup by equal key: checkpoint
collision equal hashes: true
collision equals: false
collision set size: 2
```

**Đọc kết quả đúng bản chất:**

- `p == sameCoordinates` là `false` vì có hai lần `new` tạo hai instance; `equals` là `true` vì cặp giá trị (`3`, `7`) giống nhau. Đây là khác biệt giữa **danh tính** và **giá trị**.
- Cùng tọa độ nhận mã băm `31 * 3 + 7 = 100`; khác tọa độ có thể cùng mã băm nhưng vẫn **khác nhau theo `equals`**.
- `HashSet.add(sameCoordinates)` trả `false` vì đã có phần tử tương đương; `HashSet.add(otherCoordinates)` trả `true` vì đó là tọa độ khác.
- `HashMap.get(sameCoordinates)` truy xuất được giá trị đã lưu với key `p`: `HashMap` sử dụng mã băm để tìm ứng viên và `equals` để kiểm tra tính bằng nhau của key.
- Hai tọa độ cố ý trùng mã băm vẫn cùng nằm trong `HashSet` (kích thước 2). **Trùng hash không có nghĩa hai đối tượng bằng nhau.** Mã băm chỉ hỗ trợ tổ chức tra cứu.

Bảng kiểm nhanh:

| Kiểm tra | Kỳ vọng | Lý do |
| --- | --- | --- |
| `p.equals(p)` | `true` | Phản xạ. |
| `p.equals(new Point2D(3, 7))` | `true` | So sánh tọa độ. |
| `p.equals(new Point2D(3, 8))` | `false` | Khác `y`. |
| `p.equals(null)` | `false` | Không đối tượng nào bằng `null`. |
| `p.equals("3,7")` | `false` | Khác kiểu. |
| `new Point2D(-1, 0).equals(new Point2D(-1, 0))` | `true` | Số âm vẫn là giá trị hợp lệ. |
| `equals` là `true` giữa hai đối tượng | `hashCode` bằng nhau | Hợp đồng bắt buộc. |
| `hashCode` bằng nhau giữa hai đối tượng | **Chưa đủ kết luận** | Va chạm mã băm là hợp lệ. |

## 5. Kiểm tra hợp đồng Object một cách có hệ thống

### Hợp đồng equals(Object)

Các tính chất cần kiểm tra:

1. **Phản xạ (reflexive):** với tham chiếu không null `a`, `a.equals(a)` phải là `true`.
2. **Đối xứng (symmetric):** `a.equals(b)` và `b.equals(a)` luôn cho cùng kết quả.
3. **Bắc cầu (transitive):** nếu `a.equals(b)` và `b.equals(c)` đều `true` thì `a.equals(c)` cũng phải `true`.
4. **Nhất quán (consistent):** gọi nhiều lần với cùng trạng thái đầu vào phải cho cùng kết quả.
5. **Non-null:** với mọi tham chiếu `a` không null, `a.equals(null)` phải là `false`.

Cài đặt `Point2D` đáp ứng các tính chất này do quyết định equality **chỉ dựa trên hai giá trị nguyên không đổi**. Phản xạ được tối ưu bằng `this == obj`; các tính chất còn lại được bảo đảm bởi phép bằng nhau của hai cặp tọa độ nguyên.

### Hợp đồng hashCode()

1. **Nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()` bắt buộc đúng.**
2. Nếu không có trạng thái liên quan đến `equals` thay đổi, mã băm của một đối tượng phải nhất quán giữa các lần gọi trong cùng lần thực thi.
3. **Nếu `a.equals(b) == false`, hai hash code không bắt buộc khác nhau.** Mọi thuật toán ánh xạ lượng giá trị lớn vào `int` đều có thể va chạm.

Chỉ override `equals` mà quên `hashCode` sẽ gây lỗi khó nhận ra trong `HashSet`, `HashMap` hoặc các cấu trúc dựa trên hash. Chiều ngược lại, chỉ override `hashCode` mà không override `equals` vẫn không làm hai instance khác nhau trở nên bằng nhau về giá trị.

### Hợp đồng toString()

`toString()` của `Object` không bắt buộc các tính chất tương đương nghiêm ngặt như `equals/hashCode`. Tuy nhiên, biểu diễn hữu ích nên mô tả nội dung, dễ đọc, nhất quán và tránh phụ thuộc thứ tự/tác động phụ ngoài ý muốn. Không sử dụng việc so sánh `toString()` thay cho `equals()`: hai lớp khác nhau có thể hiển thị giống nhau, và format chuỗi có thể được đổi để cải thiện log mà không đổi ý nghĩa bình đẳng.

## 6. Vì sao immutable object đặc biệt phù hợp làm key?

Giả sử lớp có setter cho `x` hoặc `y`. Sau khi đưa key vào `HashMap`, đổi tọa độ có thể khiến `hashCode()` thay đổi và `equals()` không còn tương ứng với vị trí key ban đầu trong bảng hash. Hậu quả: `map.get(key)` có thể không tìm ra mapping vừa ghi, ngay cả khi sử dụng **cùng tham chiếu key**. Đây là lỗi thiết kế, không phải lỗi của `HashMap`.

Đối tượng bất biến ngăn loại sai sót này: nội dung tham gia `equals/hashCode` được chốt ở constructor. Hãy coi quy tắc là: **mọi trường dùng để tính equality/hash của hash key phải có giá trị ổn định trong toàn bộ thời gian key tồn tại trong collection**.

Nếu cần “di chuyển” một tọa độ, tạo một instance mới:

```java
Point2D oldPoint = new Point2D(3, 7);
Point2D movedPoint = new Point2D(oldPoint.x() + 1, oldPoint.y());
// oldPoint vẫn là (3, 7); movedPoint là (4, 7).
```

Đoạn trên **minh họa API, không phải chương trình độc lập**; chạy nó trong một phương thức sau khi đã biên dịch `Point2D.java`. Tránh thực hiện thay đổi ngầm bên trong `translate` kiểu mutating; nếu bổ sung phương thức dịch chuyển, phương thức đó nên **trả về một `Point2D` mới**.

**Lưu ý về tràn số:** `oldPoint.x() + 1` trong Java dùng phép toán `int`; nếu giá trị cũ là `Integer.MAX_VALUE`, kết quả sẽ quay sang `Integer.MIN_VALUE` theo số học `int`. Nếu yêu cầu miền tọa độ cấm tràn, kiểm tra trước hoặc dùng `Math.addExact` và xử lý `ArithmeticException`. Điều này độc lập với hợp đồng `equals/hashCode`.

## 7. Những cách cài đặt sai thường gặp

### Sai 1: So sánh đối tượng bằng == thay cho equals

```java
new Point2D(3, 7) == new Point2D(3, 7) // false
```

Hai lần `new` sinh hai đối tượng khác nhau. Dùng `equals` để trả lời câu hỏi **tọa độ có trùng không**; dùng `==` khi thực sự cần kiểm tra **cùng instance trong bộ nhớ**.

### Sai 2: Chỉ so sánh một trường

```java
// Sai: bỏ qua y
return x == other.x;
```

Khi ấy (`3`, `7`) và (`3`, `8`) bị coi là một tọa độ. Đặc tả yêu cầu **cả x và y** tham gia.

### Sai 3: Chỉ override equals

```java
@Override
public boolean equals(Object obj) {
    // ... so sánh tọa độ ...
}
// Thiếu hashCode(): kế thừa identity-based hashCode từ Object.
```

Đây là **mã minh họa lỗi, không phải lớp có thể chạy độc lập**. Những đối tượng bằng nhau theo `equals` có thể bị hash khác nhau, khiến `HashMap/HashSet` không thực hiện đúng điều bạn mong đợi.

### Sai 4: Chỉ override hashCode hoặc dùng hashCode để quyết định equals

```java
// Sai: va chạm hash sẽ bị nhầm thành equality.
return this.hashCode() == other.hashCode();
```

Ví dụ `Point2D(0, 31)` và `Point2D(1, 0)` là hai tọa độ khác nhau dù chung hash 31. `equals` phải so sánh dữ liệu có ý nghĩa, không suy ngược từ hash.

### Sai 5: Dùng trường có thể sửa để tạo hash key

Ngay cả nếu trường được khai báo `private`, setter hoặc trả ra một mảng mutable có thể khiến nội dung khóa thay đổi. Với hai `int` và không setter, lớp hiện tại tránh được nguy cơ đó. Nếu sau này thêm `List`, mảng hoặc `Date`, phải thiết kế defensive copy và getter an toàn khi cần giữ bất biến sâu.

### Sai 6: Sai chữ ký hoặc quên @Override

`equals(Point2D)` **không** thay thế `equals(Object)`. Luôn khai báo phương thức đúng chữ ký và gắn `@Override`. Nếu để IDE tự tạo `equals/hashCode`, vẫn phải kiểm tra danh sách trường đã chọn tương ứng đúng yêu cầu business.

### Sai 7: Mở rộng lớp nhưng không thiết kế lại tính đối xứng

Một lớp tọa độ có thể kế thừa làm `ColoredPoint` với thuộc tính màu. Nếu lớp cha cho phép subclass bằng nhau khi cùng `x,y`, còn lớp con yêu cầu cả màu, có thể xuất hiện `base.equals(colored) == true` nhưng `colored.equals(base) == false`. Dùng `final class Point2D` ngăn tình huống kế thừa này. Nếu bài toán cần hệ phân cấp, phải thiết kế chính sách equality cho **toàn bộ hệ** một cách nhất quán; thay kiểm tra `instanceof` bằng `getClass()` cũng có đánh đổi và cần xét riêng.

## 8. So sánh với record trong Java 17+

Từ Java 16, `record` là cách khai báo ngắn gọn cho một nhóm dữ liệu bất biến theo mức độ cấu trúc. Nếu bài toán không yêu cầu tự tay thực hành ba phương thức, ta có thể viết:

```java
public record Point2DRecord(int x, int y) {}
```

Đoạn này cần đặt trong file `Point2DRecord.java`. Trình biên dịch tự tạo constructor chuẩn, accessor `x()`/`y()`, `equals`, `hashCode` và `toString` dựa trên các thành phần record. Hai bản ghi `Point2DRecord(3, 7)` bằng nhau về giá trị; chuỗi toString mặc định có dạng `Point2DRecord[x=3, y=7]`, khác định dạng thủ công của `Point2D`. Không yêu cầu hash code của record phải trùng con số `100` trong ví dụ lớp `Point2D`.

**Record không bảo đảm deep immutability:** nếu một component là mảng hoặc kiểu mutable, tham chiếu component là final nhưng nội dung bên trong vẫn có thể thay đổi. Muốn bất biến sâu, vẫn phải xem xét sao chép phòng vệ và cách xây dựng logic equality cho component đó.

Trong bài thực hành này, **tự triển khai `Point2D`** có giá trị học tập vì buộc ta hiểu và kiểm tra hợp đồng `Object`; `record` là phương án ngắn gọn để cân nhắc ở dự án thực tế khi phù hợp.

## 9. Bài tự luyện và tiêu chí hoàn thành

Để tự kiểm tra, thử các thay đổi sau trong bản sao chương trình và dự đoán trước output:

1. Tạo `new Point2D(-4, 0)` hai lần. Hai instance `==` có bằng nhau không? `equals` thì sao? Cặp hash có giống nhau không?
2. Thay `otherCoordinates` thành `new Point2D(3, 7)`. `set.add(otherCoordinates)` đổi từ `true` sang gì, và kích thước set khi ấy là bao nhiêu?
3. Thử `Point2D(0, 31)` và `Point2D(1, 0)`. Vì sao `HashSet` vẫn chứa cả hai mặc dù `hashCode()` bằng nhau?
4. Thêm phương thức `translate(int dx, int dy)` trả về điểm mới; xác minh điểm gốc và hash code của nó vẫn nguyên. Nếu muốn phát hiện tràn `int`, có thể dùng `Math.addExact`.
5. Tạm thời xóa `hashCode()` trong một bản thử nghiệm và chạy lại việc tra cứu `HashMap` bằng một key tương đương được tạo riêng. Giải thích vì sao chương trình không còn đảm bảo hoạt động đúng trong collection dựa trên hash.

**Tiêu chí đạt bài:**

- Lớp `Point2D` là `final`; `x` và `y` là `private final int`; có constructor đầy đủ, accessor, không có setter.
- `equals(Object)` kiểm tra đúng kiểu, xử lý `null`, và so sánh **cả hai** tọa độ.
- `hashCode()` sử dụng đúng những trường mà `equals()` sử dụng; ổn định sau khi khởi tạo.
- `toString()` hiển thị đúng hai tọa độ và không tác động trạng thái.
- Hai object cùng tọa độ được `HashSet` coi là một phần tử, có thể dùng thay nhau để tra cứu `HashMap`.
- Hai object có hash trùng nhưng khác tọa độ vẫn là hai phần tử khác nhau.
- Demo biên dịch với Java 17+ và tạo ra output nêu trên.

## 10. Kết luận kiến thức

Ba phương thức `equals()`, `hashCode()` và `toString()` phục vụ các mục đích khác nhau: **so sánh giá trị**, **hỗ trợ collection dựa trên hash**, và **biểu diễn dễ đọc**. Xây dựng `Point2D` bất biến khiến những quyết định về equality và hash ổn định, phù hợp để dùng như một value object. Khi mở rộng hoặc thay đổi định nghĩa tọa độ, luôn xem xét lại *cả* `equals` và `hashCode`, đồng thời kiểm chứng tác động lên `HashSet`/`HashMap`.

## Tài liệu tham khảo

- [Java SE 17 — Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): các yêu cầu về tính tương đương.
- [Java SE 17 — Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): hợp đồng khi dùng đối tượng trong cấu trúc hash.
- [Java SE 17 — Object.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()): biểu diễn chuỗi của đối tượng.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) và [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): hành vi của các collection dùng băm.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): API nền của bản ghi.