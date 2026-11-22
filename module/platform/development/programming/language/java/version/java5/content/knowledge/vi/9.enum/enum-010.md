# So sánh hằng enum và thứ tự tự nhiên

## 1. “Cùng hằng” và “đứng trước” là hai câu hỏi khác nhau

Khi làm việc với enum, cần phân biệt:

| Câu hỏi | Công cụ phù hợp |
| --- | --- |
| Hai biến có cùng tham chiếu đến một hằng không? | `==`, `!=`, hoặc `equals` |
| Một hằng đứng trước hay sau hằng khác theo khai báo? | `compareTo` |
| Cần thứ tự theo mức độ nghiệp vụ, tên hoặc tiêu chí riêng? | `Comparator` |

Ví dụ:

```java
enum Severity {
    MEDIUM,
    LOW,
    HIGH
}
```

Thứ tự tự nhiên của enum này là:

```text
MEDIUM → LOW → HIGH
```

vì đó là thứ tự khai báo. Java không tự hiểu `LOW`, `MEDIUM`, `HIGH` là các mức độ tăng dần theo ý nghĩa tiếng Anh.

Các quy tắc dưới đây vẫn áp dụng trong Java hiện đại. Ví dụ hoàn chỉnh dùng Java 17+.

## 2. Dùng == để kiểm tra cùng một hằng

```java
Severity first = Severity.LOW;
Severity second = Severity.valueOf("LOW");

System.out.println(first == second); // true
```

Hai biến cùng trỏ tới hằng `LOW` của cùng kiểu enum. `valueOf` không tạo một đối tượng enum mới chỉ vì được gọi từ chuỗi.

Vì hằng enum là những đối tượng có danh tính được ngôn ngữ kiểm soát, `==` là cách rõ ràng để kiểm tra một giá trị có phải một hằng cụ thể hay không:

```java
if (first == Severity.LOW) {
    System.out.println("low");
}
```

`!=` kiểm tra chiều ngược lại:

```java
boolean different = Severity.LOW != Severity.HIGH; // true
```

Không cần chuyển sang chuỗi rồi so sánh tên. So sánh `first.name()` với `"LOW"` làm mất lợi ích kiểm tra trực tiếp bằng kiểu enum và có thể gây lỗi khi `first` là `null`.

### 2.1. == an toàn với null

```java
Severity missing = null;

System.out.println(missing == Severity.LOW); // false
System.out.println(missing != Severity.LOW); // true
System.out.println(missing == null);         // true
```

Đây là các phép so sánh tham chiếu, không phải lời gọi phương thức trên `missing`, nên không ném `NullPointerException`.

Điều đó không làm một API tự chấp nhận `null`. Nếu thiếu mức độ là lỗi, vẫn cần kiểm tra theo hợp đồng tại nơi nhận dữ liệu.

### 2.2. Hai enum khác kiểu không trở thành cùng giá trị vì trùng tên

```java
enum Priority { LOW, HIGH }
enum Severity { LOW, HIGH }
```

`Priority.LOW` và `Severity.LOW` thuộc hai kiểu khác nhau. Một phép so sánh trực tiếp giữa hai kiểu enum không liên quan bằng `==` bị trình biên dịch từ chối:

```java
// Không biên dịch:
// boolean same = Priority.LOW == Severity.LOW;
```

Đó là kiểm tra hữu ích: nó phát hiện việc trộn hai miền giá trị không cùng ý nghĩa.

Không chuyển cả hai sang chuỗi chỉ để phép so sánh chạy được. Nếu nghiệp vụ có quan hệ ánh xạ giữa hai enum, hãy thiết kế phép ánh xạ đó tường minh.

## 3. equals() của enum cũng kiểm tra danh tính hằng

```java
Severity value = Severity.LOW;

System.out.println(value.equals(Severity.LOW));  // true
System.out.println(value.equals(Severity.HIGH)); // false
```

`Enum.equals(Object)` là phương thức final. Một enum không ghi đè nó để tự định nghĩa rằng hai hằng khác nhau “bằng nhau” vì có cùng mã hoặc cùng điểm.

Nếu cần so sánh một thuộc tính, hãy gọi tên đúng quan hệ:

```java
boolean sameRank = first.rank() == second.rank();
```

Đoạn này giả sử enum có phương thức `rank()` như ví dụ đầy đủ bên dưới. “Cùng rank” không tự đồng nghĩa với “cùng hằng”.

### 3.1. Vị trí null ảnh hưởng lời gọi equals

```java
Severity missing = null;

System.out.println(Severity.LOW.equals(missing)); // false
// missing.equals(Severity.LOW);                 // NullPointerException
```

Nếu cả hai giá trị có thể thiếu, `Objects.equals` có thể diễn đạt so sánh có xử lý `null`:

```java
System.out.println(java.util.Objects.equals(null, null)); // true
```

Với so sánh một biến enum với một hằng đã biết, `value == Severity.LOW` thường ngắn và dễ đọc.

### 3.2. equals nhận Object nên không chặn mọi nhầm kiểu ở biên dịch

```java
boolean same = Priority.LOW.equals(Severity.LOW); // false
```

Dòng này biên dịch vì tham số của `equals` là `Object`, nhưng hai giá trị không bằng nhau. Phép `==` trực tiếp giữa hai biến có kiểu enum khác nhau ở mục trước giúp phát hiện nhầm miền ngay khi biên dịch.

Không cần hiểu rằng `equals` “sai” cho enum; hai cách có cùng ý nghĩa danh tính khi so sánh các hằng cùng kiểu, nhưng kiểm tra kiểu và cách xử lý `null` ở cú pháp gọi khác nhau.

## 4. compareTo(): thứ tự tự nhiên là thứ tự khai báo

Enum đã có khả năng so sánh qua `Comparable` phù hợp với chính kiểu enum. Ví dụ:

```java
int comparison = Severity.MEDIUM.compareTo(Severity.LOW);
```

Với khai báo `MEDIUM, LOW, HIGH`, kết quả là số âm vì `MEDIUM` đứng trước `LOW`.

Hợp đồng cần dùng là dấu của kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| Nhỏ hơn 0 | Hằng bên trái đứng trước |
| Bằng 0 | Cùng hằng |
| Lớn hơn 0 | Hằng bên trái đứng sau |

Ví dụ:

```java
boolean before = Severity.MEDIUM.compareTo(Severity.LOW) < 0;
boolean after = Severity.HIGH.compareTo(Severity.LOW) > 0;
boolean same = Severity.LOW.compareTo(Severity.LOW) == 0;
```

Không viết logic đòi kết quả phải đúng `-1` hoặc `1`. API so sánh được sử dụng theo dấu; số âm hoặc dương có thể có độ lớn khác.

### 4.1. Không có toán tử < hoặc > trực tiếp cho enum

```java
// Không biên dịch:
// boolean before = Severity.LOW < Severity.HIGH;
```

Dùng `compareTo` nếu thật sự muốn thứ tự khai báo. Enum không tự chuyển thành số nguyên cho các toán tử quan hệ đó.

### 4.2. Chỉ so sánh thứ tự trong cùng kiểu enum

Một `Severity` không có hợp đồng `compareTo(Priority)`. Mã có kiểm tra kiểu sẽ chặn việc truyền enum khác kiểu.

Cũng không nên đòi các hằng phải có cùng `getClass()` mới được so sánh. Những hằng có thân lớp riêng có thể có lớp thực tế khác nhau, nhưng vẫn thuộc cùng một kiểu enum và có thứ tự tự nhiên của kiểu đó.

### 4.3. compareTo không tự xử lý null như một mức độ đặc biệt

```java
// Severity.LOW.compareTo(null); // Ném NullPointerException.
```

Nếu biến bên trái là `null`, việc gọi phương thức trên nó cũng ném `NullPointerException`.

Muốn đưa giá trị thiếu lên đầu hoặc xuống cuối danh sách, cần một comparator có chính sách `null` tường minh.

## 5. ordinal(): vị trí khai báo, không phải mức độ nghiệp vụ

`ordinal()` trả vị trí bắt đầu từ 0:

```text
MEDIUM → 0
LOW    → 1
HIGH   → 2
```

Nó giải thích mối liên hệ giữa thứ tự tự nhiên và khai báo. Tuy nhiên, mã ứng dụng thường nên dùng `compareTo` thay vì tự trừ ordinal để diễn đạt so sánh thứ tự.

Các giới hạn:

- Sắp xếp lại hằng đổi quan hệ thứ tự tương ứng.
- Thêm hằng có thể đổi ordinal của các hằng đứng sau.
- Giá trị ordinal không tự mang ý nghĩa như độ khẩn cấp, quyền truy cập hay mã lưu trữ.
- Không lưu ordinal như một mã bền vững nếu dữ liệu phải tồn tại qua việc thay đổi khai báo.

Với thứ tự nghiệp vụ cần kiểm soát độc lập, khai báo một trường như `rank` và một comparator tương ứng.

## 6. Comparator: tạo thứ tự theo mục đích sử dụng

Xét:

```java
enum Severity {
    MEDIUM(2),
    LOW(1),
    HIGH(3);

    private final int rank;

    Severity(int rank) {
        this.rank = rank;
    }

    public int rank() {
        return rank;
    }
}
```

Ba thứ tự có thể khác nhau:

| Tiêu chí | Thứ tự tăng dần |
| --- | --- |
| Tự nhiên, theo khai báo | `MEDIUM, LOW, HIGH` |
| Theo `rank` | `LOW, MEDIUM, HIGH` |
| Theo tên Java | `HIGH, LOW, MEDIUM` |

Không ghi đè `compareTo` để đổi thứ tự tự nhiên; phương thức đó là final trong `Enum`. Dùng một đối tượng `Comparator` riêng:

```java
Comparator<Severity> byRank = Comparator.comparingInt(Severity::rank);
Comparator<Severity> byName = Comparator.comparing(Severity::name);
```

Cần import `java.util.Comparator`.

`byName` sắp xếp theo chuỗi tên Java, không phải theo quy tắc ngôn ngữ của một nhãn đã bản địa hóa. Nếu giao diện cần thứ tự ngôn ngữ cụ thể, phải chọn tiêu chí và công cụ so sánh chuỗi thích hợp.

Có thể đảo một comparator:

```java
Comparator<Severity> highestRankFirst = byRank.reversed();
```

Điều này không thay đổi `Severity.compareTo` hoặc thứ tự của `Severity.values()`. Nó chỉ chọn một quy tắc cho thao tác nhận comparator đó.

## 7. Chương trình hoàn chỉnh

Lưu thành `EnumComparisonDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class EnumComparisonDemo {
    public enum Severity {
        MEDIUM(2),
        LOW(1),
        HIGH(3);

        private final int rank;

        Severity(int rank) {
            this.rank = rank;
        }

        public int rank() {
            return rank;
        }
    }

    public static void main(String[] args) {
        Severity first = Severity.LOW;
        Severity parsed = Severity.valueOf("LOW");
        Severity missing = null;

        System.out.println("same = " + (first == parsed));
        System.out.println("equals null = " + Severity.LOW.equals(missing));
        System.out.println("medium before low = "
                + (Severity.MEDIUM.compareTo(Severity.LOW) < 0));

        List<Severity> input =
                List.of(Severity.HIGH, Severity.LOW, Severity.MEDIUM);

        List<Severity> natural = new ArrayList<>(input);
        natural.sort(Comparator.naturalOrder());

        List<Severity> byRank = new ArrayList<>(input);
        byRank.sort(Comparator.comparingInt(Severity::rank));

        List<Severity> byName = new ArrayList<>(input);
        byName.sort(Comparator.comparing(Severity::name));

        List<Severity> withNull = new ArrayList<>(
                Arrays.asList(Severity.HIGH, null, Severity.LOW));
        withNull.sort(Comparator.nullsLast(Comparator.naturalOrder()));

        System.out.println("natural = " + natural);
        System.out.println("by rank = " + byRank);
        System.out.println("by name = " + byName);
        System.out.println("nulls last = " + withNull);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EnumComparisonDemo.java
java EnumComparisonDemo
```

Stdout chính xác:

```text
same = true
equals null = false
medium before low = true
natural = [MEDIUM, LOW, HIGH]
by rank = [LOW, MEDIUM, HIGH]
by name = [HIGH, LOW, MEDIUM]
nulls last = [LOW, HIGH, null]
```

Các danh sách được tạo bằng `ArrayList` trước khi sắp xếp vì thao tác `sort` cần thay đổi thứ tự phần tử. Danh sách ban đầu từ `List.of` không cho sửa và không được dùng trực tiếp làm đích sắp xếp.

Danh sách có `null` được tạo bằng `Arrays.asList` rồi sao chép sang `ArrayList`; `List.of` không nhận phần tử `null`.

`Comparator.nullsLast` đặt giá trị thiếu ở cuối, còn các phần tử khác dùng thứ tự tự nhiên. Nếu muốn các phần tử không null dùng thứ tự nghiệp vụ, truyền `Comparator.comparingInt(Severity::rank)` làm comparator bên trong.

## 8. Tính bằng nhau của comparator có thể khác equals

Nếu hai hằng có cùng rank, comparator chỉ xét rank có thể trả 0 dù chúng là hai hằng khác nhau:

```text
SAME_RANK_A != SAME_RANK_B
nhưng byRank.compare(SAME_RANK_A, SAME_RANK_B) == 0
```

Đây là ví dụ khái niệm, không phải các hằng trong chương trình trên.

Với sắp xếp một danh sách, điều đó chỉ diễn tả hai phần tử đồng hạng theo tiêu chí. Nhưng với `TreeSet` hoặc `TreeMap`, kết quả so sánh bằng 0 ảnh hưởng cách cấu trúc xác định phần tử hoặc khóa trùng.

Nếu cần giữ các hằng khác nhau tách biệt trong thứ tự đó, có thể thêm tiêu chí phụ:

```java
Comparator<Severity> byRankThenNatural =
        Comparator.comparingInt(Severity::rank)
                .thenComparing(Comparator.naturalOrder());
```

Tiêu chí phụ dùng thứ tự tự nhiên để phân biệt những hằng cùng rank. Với một thiết kế khác, hãy chọn tiêu chí phụ theo đúng hợp đồng cần thiết.

Đừng nhầm rằng comparator trả 0 đã thay đổi `Enum.equals`. Tính bằng nhau của hằng vẫn dựa vào danh tính; comparator mô tả một quan hệ sắp xếp cụ thể.

## 9. Thứ tự enum không tự diễn tả quy tắc chuyển trạng thái

Với enum trạng thái như:

```java
enum OrderState {
    NEW, PAID, SHIPPED, CANCELLED
}
```

`CANCELLED.compareTo(SHIPPED) > 0` chỉ nói `CANCELLED` được khai báo phía sau. Nó không nói hủy là “tiến bộ hơn” giao hàng, hoặc có thể chuyển từ trạng thái nào sang trạng thái nào.

Tương tự, một phép kiểm tra như `state.compareTo(PAID) >= 0` có thể sai ý nghĩa khi tập trạng thái có nhánh, quay lui hoặc trạng thái kết thúc độc lập.

Nếu cần biết “đã thanh toán chưa” hoặc “có được phép giao không”, dùng một thuộc tính hoặc phương thức nghiệp vụ có tên rõ ràng. Chỉ sử dụng thứ tự khi mô hình thật sự có một quan hệ tuyến tính phù hợp.

## 10. Các lỗi thường gặp và cách tự kiểm tra

| Lỗi | Điều cần kiểm tra |
| --- | --- |
| So sánh tên bằng `==` của String | So sánh trực tiếp hằng enum bằng `==` |
| Gọi `value.equals(...)` khi value có thể null | Dùng `==`, hằng làm receiver hoặc `Objects.equals` tùy nhu cầu |
| Cho rằng tên LOW luôn đứng trước HIGH | Đọc thứ tự khai báo hoặc dùng rank riêng |
| Kiểm tra `compareTo(...) == -1` | Kiểm tra `< 0`, `== 0`, `> 0` |
| Tự ghi đè `compareTo` của enum | Chọn `Comparator` |
| Dùng ordinal làm mã hoặc quy tắc nghiệp vụ | Khai báo dữ liệu nghiệp vụ riêng |
| Sort danh sách có null bằng thứ tự tự nhiên | Chọn chính sách null hoặc loại bỏ giá trị thiếu |
| Cho rằng comparator trả 0 nghĩa là cùng hằng | Phân biệt đồng hạng theo tiêu chí với `equals` |
| Dùng thứ tự khai báo để suy ra chuyển trạng thái | Thiết kế quy tắc chuyển trạng thái riêng |

Trước khi so sánh, hãy gọi đúng tên câu hỏi: cùng hằng, trước–sau theo khai báo, hay thứ tự theo một tiêu chí nghiệp vụ. Chọn công cụ theo câu hỏi đó để mã vừa rõ nghĩa vừa giữ được kiểm tra kiểu của enum.

## Tài liệu đối chiếu

- [Java Enum API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html): `equals`, `compareTo`, `ordinal` và thứ tự khai báo.
- [JLS §15.21.3 — Reference Equality Operators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.21.3): phép so sánh tham chiếu.
- [Java Comparator API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html): tiêu chí riêng, `comparingInt`, `thenComparing`, `nullsFirst` và `nullsLast`.
