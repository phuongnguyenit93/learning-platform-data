# `Object.equals()` mặc định dựa trên danh tính

## 1. Mục tiêu và khái niệm

Khi một lớp Java không ghi đè `equals(Object)`, phương thức kế thừa từ `java.lang.Object` chỉ kiểm tra **danh tính đối tượng** (object identity). Điều này giải thích tại sao hai thể hiện có cùng giá trị các trường vẫn có thể trả `false` khi gọi `equals()`.

Cần phân biệt:

- **Danh tính (identity):** hai tham chiếu có trỏ tới **đúng cùng một đối tượng** hay không.
- **Giá trị (value):** những dữ liệu đối tượng lưu giữ, chẳng hạn một điểm có `x = 2` và `y = 3`.
- **Bằng nhau theo giá trị (value equality):** quy tắc do lớp chủ động định nghĩa để coi hai đối tượng có các giá trị liên quan là bằng nhau.

`Point p1 = new Point(2, 3);` và `Point p2 = new Point(2, 3);` tạo **hai đối tượng riêng**. Nếu lớp `Point` không định nghĩa lại `equals()`, `p1.equals(p2)` là `false`, dù tọa độ giống nhau. Ngược lại, `Point alias = p1;` chỉ sao chép tham chiếu; `p1` và `alias` cùng chỉ tới một đối tượng.

## 2. Cơ chế mặc định của `Object.equals()`

Mọi lớp Java thông thường kế thừa `Object` trực tiếp hoặc gián tiếp. Khi lớp không override `equals(Object)`, hành vi mặc định tương đương:

```java
public boolean equals(Object obj) {
    return this == obj;
}
```

Đoạn trên minh họa thân phương thức của `Object`, **không phải chương trình độc lập**. Với hai tham chiếu, `==` kiểm tra xem chúng có trỏ tới **cùng đối tượng**. Nó không tự duyệt tất cả các trường, không so sánh `toString()` và không kiểm tra xem hai đối tượng có “nội dung giống nhau” hay không.

| Biểu thức với `a` khác null | Kết quả nếu dùng `Object.equals()` | Giải thích |
| --- | --- | --- |
| `a.equals(a)` | `true` | Một đối tượng đồng nhất với chính nó. |
| `a.equals(alias)` khi `alias = a` | `true` | Hai biến giữ cùng tham chiếu. |
| `a.equals(b)` khi `b` là đối tượng mới | `false` | Hai thực thể khác danh tính, dù các trường bằng nhau. |
| `a.equals(null)` | `false` | Không đối tượng nào đồng nhất với null. |
| `a == alias` | `true` | `==` so danh tính của tham chiếu. |

**Chú ý dispatch động:** `a.equals(b)` thực thi triển khai `equals` của lớp thực tế của `a`. Vì thế `equals()` chỉ đồng nghĩa với `==` khi triển khai được gọi là phương thức mặc định của `Object` (hoặc một override cố ý giữ cùng logic). Những lớp như `String` có quy tắc khác.

## 3. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `ObjectEqualsDemo.java` với đúng tên public class:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectEqualsDemo {
    // Kế thừa equals/hashCode mặc định của Object.
    static final class PlainPoint {
        final int x;
        final int y;

        PlainPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    // Chủ động định nghĩa equality dựa trên hai tọa độ.
    static final class ValuePoint {
        final int x;
        final int y;

        ValuePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ValuePoint point)) {
                return false;
            }
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    public static void main(String[] args) {
        PlainPoint first = new PlainPoint(2, 3);
        PlainPoint alias = first;
        PlainPoint second = new PlainPoint(2, 3);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first.equals(alias): " + first.equals(alias));
        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.equals(null): " + first.equals(null));

        ValuePoint v1 = new ValuePoint(2, 3);
        ValuePoint v2 = new ValuePoint(2, 3);
        Set<ValuePoint> points = new HashSet<>();
        points.add(v1);

        System.out.println("v1 == v2: " + (v1 == v2));
        System.out.println("v1.equals(v2): " + v1.equals(v2));
        System.out.println("points.contains(v2): " + points.contains(v2));

        String s1 = new String("java");
        String s2 = new String("java");
        System.out.println("s1 == s2: " + (s1 == s2));
        System.out.println("s1.equals(s2): " + s1.equals(s2));
        System.out.println("Objects.equals(null, null): " +
                Objects.equals(null, null));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac ObjectEqualsDemo.java
java ObjectEqualsDemo
```

Kết quả:

```text
first == alias: true
first.equals(alias): true
first == second: false
first.equals(second): false
first.equals(null): false
v1 == v2: false
v1.equals(v2): true
points.contains(v2): true
s1 == s2: false
s1.equals(s2): true
Objects.equals(null, null): true
```

Phân tích:

1. `first` và `alias` cùng trỏ tới một `PlainPoint`, nên cả `==` và `equals()` mặc định đều là `true`.
2. `first` và `second` là hai lần `new` độc lập: tọa độ giống nhau nhưng danh tính khác nhau, nên cả hai phép so sánh là `false`.
3. `v1` và `v2` là hai `ValuePoint` riêng: `==` là `false` nhưng `equals()` là `true` vì lớp tự so sánh `x` và `y`.
4. `HashSet` tìm được `v2` dù chỉ đã thêm `v1` bởi vì `equals()` và `hashCode()` của `ValuePoint` nhất quán.
5. Hai lần `new String("java")` tạo hai đối tượng `String` riêng. `String` đã override `equals()` để so nội dung chuỗi, nên `==` là `false` và `equals()` là `true`.
6. `Objects.equals(null, null)` cho `true`, thể hiện cách so sánh null-safe khác với gọi phương thức trực tiếp trên null.

## 4. Khi nào nên giữ hoặc ghi đè `equals()`?

**Giữ mặc định** khi sự khác nhau giữa các thể hiện là điều có ý nghĩa: hai đối tượng độc lập phải được phân biệt ngay cả khi một số thuộc tính trùng nhau. Đây là lựa chọn thiết kế hợp lệ, không phải lỗi Java.

**Ghi đè** khi lớp đại diện cho một giá trị, chẳng hạn tọa độ, số tiền (bao gồm đơn vị tiền), khóa định danh, hoặc một value object với quy tắc rõ ràng. Khi đó quyết định các trường nào thực sự tạo nên sự bằng nhau. Trong `ValuePoint`:

- `this == other` trả lời nhanh trường hợp cùng tham chiếu.
- `instanceof ValuePoint point` xử lý đúng trường hợp null hoặc sai kiểu trước khi truy cập trường; cú pháp pattern matching này hỗ trợ ở Java 17.
- `x == point.x && y == point.y` so các thành phần tạo nên giá trị.
- `hashCode()` dùng đúng những thành phần đó, tương thích với `equals()`.

Java record có thể thích hợp cho các value object đơn giản. Ví dụ `record Point(int x, int y) {}` được Java tạo `equals()`/`hashCode()` dựa trên các component; **đó là hành vi riêng của record**, không phải `Object.equals()` mặc định.

### Hợp đồng của `equals`

Một triển khai `equals` đúng cần đảm bảo:

1. **Phản xạ:** `x.equals(x)` là `true` nếu `x` khác null.
2. **Đối xứng:** nếu `x.equals(y)` là `true` thì `y.equals(x)` cũng là `true`.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` là `true` thì `x.equals(z)` là `true`.
4. **Nhất quán:** khi trạng thái tham gia phép so sánh không đổi, gọi lại không tự ý cho kết quả khác.
5. **Với null:** `x.equals(null)` là `false` nếu `x` khác null.

So danh tính mặc định của `Object` thỏa mãn cả năm tính chất. Khi tự ghi đè, cần cân nhắc kế thừa và các trường có thể thay đổi để tránh phá vỡ hợp đồng.

### Hợp đồng giữa `equals` và `hashCode`

Khi `a.equals(b)` trả `true` thì `a.hashCode() == b.hashCode()` **bắt buộc** cũng phải là `true`. Chiều ngược lại không đúng: hai đối tượng không bằng nhau vẫn có thể cùng hash (collision). Vì vậy hash bằng nhau **không chứng minh** hai đối tượng đồng nhất.

Nếu chỉ ghi đè `equals()` theo giá trị nhưng tiếp tục dùng `Object.hashCode()`, hai đối tượng được coi là bằng nhau có thể nhận hash khác nhau và phá vỡ giả định của `HashMap`/`HashSet`. Do đó khi thay đổi logic equality phải thiết kế `hashCode()` tương ứng. Tránh thay đổi các trường tham gia equality/hash trong thời gian đối tượng đang là khóa của hash collection.

`Object.hashCode()` mặc định hỗ trợ hợp đồng cho equality theo danh tính. Giá trị trả về **không được đảm bảo là địa chỉ bộ nhớ** hay duy nhất toàn cục. `System.identityHashCode(obj)` lấy hash theo cơ chế danh tính kể cả khi lớp override `hashCode()`, nhưng vẫn có khả năng trùng hash nên không thể thay `==`.

## 5. Những tình huống dễ hiểu sai

| Tình huống | Cách hiểu đúng |
| --- | --- |
| `new String("A").equals(new String("A"))` | `true` vì `String` override theo nội dung, không phải hành vi mặc định. |
| Hai mảng `new int[]{1, 2}` được tạo riêng | Mảng kế thừa `Object.equals()`, nên hai mảng khác danh tính. Dùng `Arrays.equals(a, b)` để so các phần tử mảng một chiều; cân nhắc `Arrays.deepEquals` cho mảng lồng nhau. |
| Hai `List` chứa dãy phần tử tương ứng bằng nhau | Các triển khai `List` chuẩn so theo phần tử; không thể suy từ hành vi mặc định của `Object`. |
| `a.equals(null)` | `false` nếu `a` khác null. Nhưng `null.equals(a)` ném `NullPointerException`, vì null không có phương thức để gọi. |
| `Objects.equals(a, b)` | Hai null được coi bằng nhau, một null một khác là không bằng, còn lại gọi `a.equals(b)`. |
| `==` với kiểu nguyên thủy | So **giá trị nguyên thủy**, không so danh tính. Chỉ khi toán hạng là tham chiếu mới kiểm tra cùng đối tượng. |
| `==` với các đối tượng wrapper hoặc chuỗi | Kết quả có thể chịu ảnh hưởng boxing, cache hoặc string interning. Khi mục đích là so giá trị, dùng `equals()` phù hợp. |

**Không dựa vào `toString()`, `hashCode()` hoặc địa chỉ giả định** để đánh giá danh tính. `hashCode()` không phải khóa định danh duy nhất. Cũng không giả định hai đối tượng mới luôn có tất cả trạng thái khác nhau; hai đối tượng riêng có thể cùng giá trị, và chính điểm này làm nổi bật khác biệt giữa identity và equality.

## 6. Chọn công cụ so sánh phù hợp

| Nhu cầu | Sử dụng | Điều cần kiểm tra |
| --- | --- | --- |
| Hai biến có trỏ đúng cùng đối tượng? | `a == b` | So tham chiếu; cũng dùng `a == null`. |
| Hai đối tượng có bằng nhau theo quy tắc của lớp? | `a.equals(b)` | `a` phải khác null; đọc hợp đồng `equals` của lớp. |
| So sánh có thể gặp null? | `Objects.equals(a, b)` | Hai null được xem là bằng nhau. |
| Viết value object của mình? | Override `equals()` và `hashCode()` cùng nhau, hoặc dùng record | Chọn rõ các thành phần tham gia equality. |
| Tra cứu trong `HashMap`/`HashSet`? | Theo `equals()` kết hợp `hashCode()` | Hai đối tượng bằng nhau phải có hash bằng nhau; khóa không nên đổi trạng thái có ảnh hưởng đến hash. |

## 7. Tự kiểm tra

**Câu 1:** Nếu `PlainPoint b = a;`, `a.equals(b)` và `a == b` trả gì khi `PlainPoint` không override `equals`?

**Trả lời:** Cả hai là `true` vì cùng tham chiếu.

**Câu 2:** Hai lần `new PlainPoint(2, 3)` có bằng nhau theo `Object.equals()` không?

**Trả lời:** Không. Hai đối tượng riêng có danh tính khác nhau, dù các trường trùng nhau.

**Câu 3:** Vì sao `new String("x").equals(new String("x"))` là `true`?

**Trả lời:** `String` có triển khai `equals()` so nội dung chuỗi; nó không dùng cách so danh tính mặc định.

**Câu 4:** Hai đối tượng có mã hash bằng nhau thì có chắc chắn `equals()` bằng nhau hoặc `==` không?

**Trả lời:** Không. Hash collision có thể xảy ra. Chỉ có chiều “`equals()` bằng nhau ⇒ mã hash bằng nhau” là điều hợp đồng bắt buộc.

**Ghi nhớ:** `Object.equals()` mặc định trả lời câu hỏi **“có phải cùng một đối tượng không?”**. Câu hỏi **“có cùng giá trị có ý nghĩa không?”** cần một định nghĩa `equals()` riêng của lớp.