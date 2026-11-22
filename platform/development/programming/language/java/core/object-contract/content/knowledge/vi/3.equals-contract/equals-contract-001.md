# `equals()` định nghĩa quan hệ tương đương trên các tham chiếu khác `null`

## 1. Mục tiêu và phạm vi

Trong Java, `Object.equals(Object)` là phương thức để một đối tượng trả lời câu hỏi: “Đối tượng này có được xem là bằng đối tượng kia theo quy tắc của kiểu dữ liệu hay không?”. Triển khai mặc định trong `Object` chỉ coi hai tham chiếu bằng nhau khi chúng cùng trỏ đến **một đối tượng**. Lớp có ngữ nghĩa giá trị thường ghi đè `equals` để hai đối tượng khác nhau vẫn bằng nhau khi các thuộc tính có ý nghĩa tương ứng bằng nhau.

Xét tập `D` gồm các tham chiếu đối tượng Java **khác `null`**. Định nghĩa quan hệ `~` trên `D`:

- `x ~ y` khi và chỉ khi `x.equals(y)` trả về `true`.
- Để `~` thực sự là **quan hệ tương đương**, `equals` phải có tính **phản xạ, đối xứng, bắc cầu**.
- Hợp đồng của `Object.equals` còn yêu cầu **nhất quán** trong điều kiện trạng thái liên quan không đổi và `x.equals(null)` luôn là `false` đối với `x != null`.

Cần phân biệt: các tiên đề của *quan hệ tương đương* áp dụng cho các phần tử **khác `null`** trong `D`; hai yêu cầu “nhất quán” và “khác `null`” là phần bổ sung của **hợp đồng phương thức `equals`**, không phải hai tiên đề toán học của quan hệ tương đương.

## 2. Năm điều kiện của hợp đồng `equals`

Với các tham chiếu `x`, `y`, `z` khác `null`:

| Điều kiện | Biểu thức / phát biểu | Ý nghĩa |
| --- | --- | --- |
| **Phản xạ (reflexive)** | `x.equals(x) == true` | Một đối tượng luôn bằng chính nó. |
| **Đối xứng (symmetric)** | `x.equals(y)` và `y.equals(x)` phải cho cùng kết quả | Thứ tự hai đối tượng không được quyết định kết quả bằng nhau. |
| **Bắc cầu (transitive)** | Nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)` | Ba đối tượng không thể tạo thành chuỗi “bằng, bằng, nhưng không bằng”. |
| **Nhất quán (consistent)** | Gọi nhiều lần cho cùng cặp đối tượng phải có cùng kết quả, nếu thông tin dùng bởi `equals` không thay đổi | Kết quả không được phụ thuộc ngẫu nhiên vào lần gọi, thời gian hay trạng thái ngoại lai không thuộc định nghĩa bằng nhau. |
| **Khác `null` (non-null)** | `x.equals(null) == false` | Một tham chiếu tới đối tượng thực không bằng `null`. |

### Phản xạ

`x.equals(x)` phải đúng ngay cả khi `x` là đối tượng mới tạo hoặc thuộc lớp có logic so sánh phức tạp. Một cách triển khai thường gặp là kiểm tra `this == other` trước; nhưng đây chỉ là kỹ thuật tối ưu, không thay thế việc thiết kế toàn bộ quan hệ bằng nhau.

### Đối xứng

Nếu `a.equals(b)` là `true` thì `b.equals(a)` cũng phải là `true`. Lỗi thường xuất hiện khi một lớp chấp nhận so sánh với kiểu khác nhưng kiểu đó không có quy tắc tương ứng, hoặc khi lớp con thay đổi tiêu chí so sánh của lớp cha.

Ví dụ về **thiết kế sai**: một lớp `FlexibleText` cho `equals` chấp nhận một `String` có chữ hoa/thường khác nhau. Nếu `FlexibleText("java").equals("JAVA")` trả về `true`, thì `"JAVA".equals(FlexibleText("java"))` vẫn trả về `false` bởi `String.equals` chỉ chấp nhận `String`. Hai hướng không đối xứng. Giải pháp là định nghĩa cùng miền kiểu cho cả hai phía hoặc dùng một API so sánh riêng (ví dụ `equalsIgnoreCase`) nếu muốn quy tắc khác.

### Bắc cầu

Giả sử một thiết kế so sánh hai số nguyên là bằng nhau khi khoảng cách của chúng không quá 1. Khi đó `1 ~ 2` đúng, `2 ~ 3` đúng, nhưng `1 ~ 3` sai. Quy tắc “gần bằng” này **không phù hợp để triển khai `equals`**. Nó có thể là một phép kiểm tra nghiệp vụ với tên riêng như `isNearTo`, nhưng không thể thay thế quan hệ bằng nhau có tính bắc cầu.

### Nhất quán và `null`

`equals` cần dựa trên những dữ liệu xác định ngữ nghĩa đối tượng. Nếu các dữ liệu ấy không đổi thì kết quả không được tự đổi giữa các lần gọi. Khi dữ liệu dùng để so sánh **thực sự thay đổi**, kết quả `equals` được phép thay đổi; điều này vẫn dễ gây rủi ro khi đối tượng đã được dùng làm khóa trong cấu trúc băm.

`x.equals(null)` phải trả về `false`. Ngược lại, `null.equals(x)` **không thể gọi được** và sẽ gây `NullPointerException`. Hãy phân biệt hai biểu thức đó thay vì diễn đạt chung rằng “`null` tự so sánh được”.

## 3. Phân biệt `==`, `equals` và `Objects.equals`

- Với **tham chiếu đối tượng**, `a == b` kiểm tra **đồng nhất tham chiếu**: cả hai cùng trỏ đến một đối tượng (hoặc đều là `null`).
- `a.equals(b)` áp dụng quy tắc **bằng nhau do lớp `a` định nghĩa**; nó yêu cầu `a` khác `null`. Nếu lớp không ghi đè `Object.equals`, hành vi mặc định là so sánh đồng nhất như `==`.
- `Objects.equals(a, b)` kiểm tra an toàn khi có `null`: nếu cả hai `null` thì trả về `true`; nếu chỉ một bên `null` thì `false`; nếu `a` khác `null` thì ủy quyền tới `a.equals(b)`.

`Objects.equals(null, null) == true` không mâu thuẫn với `x.equals(null) == false`: biểu thức đầu là tiện ích so sánh hai tham chiếu có thể `null`, biểu thức sau là hợp đồng của phương thức trên **một đối tượng có thật**.

Các phương thức hoặc miền giá trị khác nhau có thể định nghĩa khái niệm bằng nhau khác nhau. Khi thảo luận hợp đồng ở bài này, luôn xét kết quả của **`equals(Object)`**, không thay bằng `==` hay một phương thức gần giống tên.

## 4. Ví dụ Java 17+ đúng hợp đồng

Thiết kế `Coordinate` là một **lớp giá trị bất biến** với hai thành phần số nguyên `x`, `y`. Hai tọa độ bằng nhau khi cả `x` lẫn `y` bằng nhau. Khai báo `final` làm rõ rằng lớp không có lớp con bổ sung trạng thái so sánh.

Lưu toàn bộ chương trình sau trong tệp `EqualsContractDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class EqualsContractDemo {
    static final class Coordinate {
        private final int x;
        private final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Coordinate that)) {
                return false;
            }
            return x == that.x && y == that.y;
        }

        @Override
        public int hashCode() {
            return 31 * x + y;
        }
    }

    public static void main(String[] args) {
        Coordinate a = new Coordinate(2, 5);
        Coordinate b = new Coordinate(2, 5);
        Coordinate c = new Coordinate(2, 5);
        Coordinate different = new Coordinate(2, 6);

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("reflexive: " + a.equals(a));
        System.out.println("symmetric: " + (a.equals(b) == b.equals(a)));
        System.out.println("transitive: "
                + (!a.equals(b) || !b.equals(c) || a.equals(c)));
        System.out.println("null: " + a.equals(null));
        System.out.println("different: " + a.equals(different));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));

        Set<Coordinate> coordinates = new HashSet<>();
        coordinates.add(a);
        System.out.println("set contains b: " + coordinates.contains(b));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 EqualsContractDemo.java
java EqualsContractDemo
```

Kết quả chuẩn:

```text
a == b: false
a.equals(b): true
reflexive: true
symmetric: true
transitive: true
null: false
different: false
same hash: true
set contains b: true
```

Giải thích các bước:

1. `a` và `b` được tạo bằng hai lệnh `new` riêng, nên `a == b` là `false`; chúng có cùng cặp tọa độ nên `a.equals(b)` là `true`.
2. Kiểm tra `this == other` xử lý nhanh trường hợp chính nó và bảo đảm phản xạ; mẫu `instanceof Coordinate that` (pattern matching có trong Java 17) trả về `false` khi `other` là `null` hoặc khác kiểu.
3. So sánh hai trường `int` bằng `==` là thích hợp vì ở đây chúng là các **giá trị nguyên thủy**. Định nghĩa bằng nhau không dựa vào địa chỉ đối tượng.
4. Biểu thức “transitive” trong chương trình kiểm tra một bộ ba cụ thể: nếu hai tiền đề đúng thì kết luận phải đúng. Một ví dụ trả về `true` **không chứng minh** mọi đầu vào đều thỏa hợp đồng; cần kiểm tra thêm bằng test có hệ thống.
5. `HashSet.contains(b)` thành công dù chỉ thêm `a`, bởi `a` và `b` được coi là cùng giá trị, đồng thời mã băm tương thích.

## 5. Hợp đồng giữa `equals` và `hashCode`

Khi ghi đè `equals`, gần như luôn phải ghi đè `hashCode` cùng lúc. Hợp đồng quy định:

- Nếu `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`.
- Nếu `a.equals(b)` là `false`, mã băm **có thể giống hoặc khác nhau**; va chạm hash là hợp lệ.
- Trong một lần chạy, các lần gọi `hashCode` trên cùng đối tượng phải nhất quán khi dữ liệu dùng trong `equals` không thay đổi.

Ví dụ tọa độ sử dụng `31 * x + y`. Đây là cách phối hợp đơn giản cho hai trường `int`; phép tràn số nguyên Java vẫn được xác định, không tự làm vi phạm hợp đồng. Lưu ý hai tọa độ khác nhau **có thể** tạo cùng hash, điều đó không khiến chúng bằng nhau. Có thể chọn `Objects.hash(x, y)` khi ưu tiên cách viết tổng quát, chấp nhận chút chi phí bổ sung.

`HashMap`, `HashSet` thường tìm ứng viên trong nhóm theo `hashCode` rồi dùng `equals` để quyết định bằng nhau. Vi phạm chiều “bằng nhau ⇒ cùng hash” có thể làm thao tác `contains`, `get` hoặc phát hiện khóa trùng bị sai. Dù `equals` đúng, thay đổi dữ liệu ảnh hưởng tới hash của một khóa **sau khi đã đưa vào** cấu trúc băm cũng có thể khiến việc tra cứu không còn tìm thấy nó. Vì vậy, ưu tiên khóa **bất biến**.

## 6. Chọn các thuộc tính và miền kiểu để so sánh

Một triển khai tốt trả lời trước hai câu hỏi: **điều gì xác định danh tính giá trị** và **những kiểu nào được phép xem là bằng nhau**?

Ví dụ một mã sách có trường `isbn` và mô tả hiển thị `displayTitle`: nếu nghiệp vụ xác định sách bằng ISBN, hai đối tượng có cùng ISBN vẫn có thể bằng nhau dù tiêu đề hiển thị khác. Ngược lại, tọa độ `(x, y)` phải dùng cả hai thành phần. Cần chọn tiêu chí nhất quán với ý nghĩa dữ liệu, không tự động đưa mọi trường vào so sánh.

### Kế thừa và vấn đề đối xứng/bắc cầu

Nếu `Point` so sánh `x, y`, còn `ColorPoint extends Point` muốn so sánh thêm `color`, rất dễ có hai kết quả trái ngược: `Point.equals(ColorPoint)` chấp nhận do cùng tọa độ, nhưng `ColorPoint.equals(Point)` từ chối vì không có màu. Nếu cố cho phép mọi hướng, có thể lại phá bắc cầu giữa hai điểm có màu khác nhau và một điểm không màu.

Các phương án tùy ngữ nghĩa:

- Dùng lớp giá trị `final` khi thiết kế không cần kế thừa: đơn giản nhất để giữ một quy tắc `equals` ổn định.
- Dùng `getClass() == other.getClass()` khi muốn **chỉ bằng nhau trong cùng lớp runtime**, áp dụng nhất quán trong thứ bậc lớp; điều này cố ý không xem lớp cha và lớp con bằng nhau.
- Nếu thực sự cần bình đẳng xuyên các lớp trong quan hệ kế thừa, phải thiết kế quy tắc chung cho mọi phía và kiểm chứng đủ các tính chất. Đừng chỉ đổi `instanceof` thành `getClass` một cách máy móc.

Trong ví dụ `Coordinate` là `final` nên mẫu `instanceof Coordinate` vừa ngắn gọn vừa xác định rõ tập đối tượng có thể bằng nhau.

### Những trường hợp cần chú ý

- **Mảng Java:** hai mảng riêng có cùng phần tử vẫn không bằng nhau theo `array1.equals(array2)` (thừa hưởng so sánh tham chiếu). Dùng `Arrays.equals` cho mảng một chiều, hoặc `Arrays.deepEquals` cho mảng chứa mảng cần so sánh sâu.
- **`BigDecimal`:** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false` vì `equals` còn xét scale; trong khi `compareTo` có thể trả về `0`. Quy tắc sắp thứ tự và `equals` khác nhau có thể dẫn đến khác biệt giữa `TreeSet` và `HashSet`.
- **Số thực:** `double` có `NaN`, `-0.0`, `+0.0`; tránh chọn trực tiếp tiêu chí “khoảng sai số epsilon” cho `equals` vì dễ vi phạm bắc cầu. Khi cần biểu diễn giá trị số thực theo hợp đồng nhất quán, xem xét `Double.compare` / `Double.hashCode` hoặc quy tắc chuẩn hóa phù hợp với miền dữ liệu.
- **`record`:** Java tự sinh `equals` và `hashCode` theo các thành phần của record. Đó là điểm khởi đầu hữu ích cho mô hình giá trị, nhưng thành phần tham chiếu tới đối tượng có thể thay đổi vẫn cần được cân nhắc về tính bất biến thực tế.

## 7. Hai phản ví dụ giúp nhận ra lỗi thiết kế

### Sai đối xứng: so sánh sang kiểu khác

Đoạn **minh họa rút gọn, không phải chương trình Java độc lập** sau giả định lớp `FlexibleText` có trường `String value`:

```java
@Override
public boolean equals(Object other) {
    if (other instanceof FlexibleText text) {
        return value.equalsIgnoreCase(text.value);
    }
    if (other instanceof String text) {
        return value.equalsIgnoreCase(text); // SAI: String.equals không nhận FlexibleText
    }
    return false;
}
```

Với `FlexibleText("java")` và `"JAVA"`, lời gọi từ phía `FlexibleText` có thể đúng nhưng chiều ngược lại sai. Không dùng quy tắc này làm `equals`. Nếu muốn kiểm tra chuỗi không phân biệt hoa/thường, hãy công khai phương thức nghiệp vụ riêng hoặc chuẩn hóa dữ liệu trước khi tạo một kiểu giá trị có miền so sánh thống nhất.

### Sai bắc cầu: “gần bằng”

Giả sử `NearbyNumber.equals` trả về `true` khi hiệu tuyệt đối của hai giá trị không quá `1`. Khi giá trị là `1`, `2`, `3` thì:

```text
1 ~ 2: true
2 ~ 3: true
1 ~ 3: false
```

Hai tiền đề đều đúng nhưng kết luận sai, nên quan hệ không bắc cầu. Test chỉ một cặp có thể không thấy lỗi; cần test một **bộ ba**. Nếu ứng dụng cần khái niệm “gần nhau”, viết một hàm như `withinDistance(other, tolerance)` và không tuyên bố đó là `equals`.

## 8. Cách kiểm thử hợp đồng

Đối với lớp giá trị của bạn, chuẩn bị ít nhất ba đối tượng cùng giá trị nhưng được tạo độc lập (`a, b, c`), một đối tượng khác giá trị (`d`), một đối tượng khác kiểu và `null`. Xác nhận:

1. `a.equals(a)` đúng; với các đối tượng hợp lệ khác cũng tương tự.
2. `a.equals(b) == b.equals(a)`; thử cả cặp bằng nhau và không bằng nhau, kể cả khi khác kiểu.
3. Nếu `a.equals(b) && b.equals(c)` thì `a.equals(c)`; thử nhiều bộ ba, nhất là khi có kế thừa hoặc làm tròn số.
4. Gọi cùng cặp nhiều lần khi các trường liên quan không đổi cho cùng kết quả.
5. `a.equals(null)` sai; việc kiểm tra khác kiểu trả về `false` mà không ép kiểu sai.
6. Với mọi cặp bằng nhau, mã băm phải bằng nhau; kiểm tra thêm cách dùng thực tế trong `HashSet` và `HashMap`.
7. Nếu lớp cho phép thay đổi trạng thái, xác định rõ trường nào ảnh hưởng `equals`/`hashCode` và tránh dùng các đối tượng có hash thay đổi làm khóa.

Các lệnh kiểm tra trong `main` ở trên là ví dụ quan sát hành vi, chưa phải kiểm định đầy đủ. Với thư viện hoặc domain model quan trọng, nên có unit test theo tính chất (property-based tests) trên nhiều dữ liệu, đặc biệt test cặp kiểu cha/con và các giá trị biên nếu có.

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Viết `equals(Coordinate other)` thay vì `equals(Object other)` | Đây là **overload**, không ghi đè `Object.equals`; các collection gọi phiên bản `equals(Object)` vẫn giữ hành vi cũ. | Dùng `@Override public boolean equals(Object other)`; annotation giúp trình biên dịch phát hiện chữ ký sai. |
| So sánh trường tham chiếu bằng `==` khi cần so sánh giá trị | Hai đối tượng nội dung giống nhau có thể bị coi là khác nhau. | Dùng `Objects.equals(field1, field2)` hoặc `field.equals(...)` khi chắc chắn không `null`. |
| Quên kiểm tra `null`/kiểu trước khi ép kiểu | Có thể gây `NullPointerException` hoặc `ClassCastException` trong quá trình so sánh. | Kiểm tra `this == other` và `instanceof` (hoặc kiểm tra class) trước khi đọc trường của đối tượng kia. |
| Ghi đè `equals` nhưng không ghi đè `hashCode` tương ứng | Cấu trúc băm có thể xử lý sai hai khóa bằng nhau. | Dùng cùng tập trường quan trọng cho cả hai phương thức. |
| Thêm điều kiện bằng nhau chỉ ở lớp con | Có thể phá đối xứng/bắc cầu khi so với lớp cha. | Chọn miền kiểu và chính sách kế thừa rõ ràng; ưu tiên value class `final` nếu phù hợp. |
| Dùng ngưỡng gần đúng làm `equals` | Có thể phá bắc cầu. | Tách thao tác “gần bằng” thành phương thức riêng. |
| Dùng trường mutable của khóa trong `hashCode` | Tra cứu trong `HashMap`/`HashSet` có thể thất bại sau sửa đổi. | Dùng khóa bất biến hoặc không thay đổi các trường tham gia so sánh khi đã lưu trong cấu trúc băm. |

## 10. Ghi nhớ

Một `equals(Object)` hợp lệ trên các đối tượng khác `null` phải tạo ra **quan hệ tương đương**: phản xạ, đối xứng, bắc cầu. Hợp đồng Java còn đòi hỏi nhất quán khi dữ liệu so sánh không đổi và `x.equals(null) == false`. Nếu đã định nghĩa bằng nhau theo giá trị, hãy bảo đảm `hashCode` tương thích. Điểm quan trọng nhất khi cài đặt là xác định **đúng ý nghĩa bằng nhau và miền kiểu**, sau đó dùng test cho cả các cặp và bộ ba đối tượng, không chỉ một ví dụ có kết quả mong đợi.