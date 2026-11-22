# Tách phép so khớp gần đúng khỏi `equals()` khi không tạo quan hệ tương đương

Trong Java, `equals(Object)` biểu thị **bằng nhau về mặt logic** theo hợp đồng của `Object`. Còn các câu hỏi như “hai số đo lệch nhau không quá 1°C?”, “hai tọa độ cách nhau dưới 10 mét?”, “hai chuỗi có độ tương tự trên 90%?” thường là **phép so khớp gần đúng**. Chúng có thể hữu ích trong nghiệp vụ, nhưng không nhất thiết tạo ra quan hệ tương đương. Nếu đưa chúng vào `equals()`, kết quả của `HashSet`, `HashMap` và các phép so sánh trong chương trình có thể khó hiểu hoặc sai.

**Nguyên tắc:** giữ `equals()` cho một định nghĩa bằng nhau ổn định, có tính tương đương; thể hiện phép gần đúng qua API riêng như `isCloseTo`, `matchesWithinTolerance` hoặc `isSimilarTo`, với quy tắc và ngưỡng rõ ràng.

## 1. Thế nào là một quan hệ tương đương?

Một quan hệ `~` trên các đối tượng là *quan hệ tương đương* khi thỏa ba tính chất:

| Tính chất | Diễn đạt | Ví dụ với đối tượng `a`, `b`, `c` |
| --- | --- | --- |
| Phản xạ (*reflexive*) | Mỗi đối tượng bằng chính nó | `a ~ a` |
| Đối xứng (*symmetric*) | Nếu `a` bằng `b` thì `b` bằng `a` | `a ~ b ⇒ b ~ a` |
| Bắc cầu (*transitive*) | Nếu `a` bằng `b` và `b` bằng `c`, thì `a` phải bằng `c` | `a ~ b` và `b ~ c` ⇒ `a ~ c` |

Hợp đồng `Object.equals(Object)` trong Java đòi hỏi các tính chất này. Nó còn yêu cầu **nhất quán** (khi thông tin dùng để so sánh không đổi, gọi lặp lại phải cho cùng kết quả) và `x.equals(null)` luôn trả `false`. Khi ghi đè `equals()`, phải đồng thời bảo đảm: nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc.

Quan hệ tương đương chia tập đối tượng thành các nhóm bằng nhau rõ ràng: hai đối tượng trong cùng nhóm phải được xem là bằng nhau, bất kể thứ tự so sánh. Điều này đặc biệt quan trọng với các collection tổ chức phần tử theo tính bằng nhau.

## 2. Vì sao so khớp bằng khoảng sai số thường không bắc cầu?

Giả sử hai nhiệt độ “gần nhau” nếu độ chênh lệch tuyệt đối không quá `1.0`:

~~~java
static boolean close(double x, double y, double tolerance) {
    return Math.abs(x - y) <= tolerance;
}
~~~

Đây chỉ là **đoạn minh họa quy tắc**, chưa có kiểm tra `NaN`, vô cực và ngưỡng đầu vào; ví dụ chạy đầy đủ ở phần sau sẽ có kiểm tra đó.

Xét ba giá trị:

- `a = 0.0` và `b = 0.6`: chênh lệch `0.6`, nên `a ~ b` là `true`.
- `b = 0.6` và `c = 1.2`: chênh lệch `0.6`, nên `b ~ c` là `true`.
- `a = 0.0` và `c = 1.2`: chênh lệch `1.2`, nên `a ~ c` là `false`.

Ta có `a ~ b` và `b ~ c` nhưng **không có** `a ~ c`. Như vậy, quy tắc “chênh lệch ≤ ngưỡng” **không có tính bắc cầu** với ngưỡng dương nói chung. Dù quy tắc này có phản xạ và đối xứng cho số hữu hạn và ngưỡng hợp lệ, chỉ cần hỏng một trong ba tính chất là nó không còn là quan hệ tương đương.

Đó là lý do **không nên** viết:

~~~java
// Sai về hợp đồng equals: minh họa điều KHÔNG nên làm.
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof Temperature other)) {
        return false;
    }
    return Math.abs(celsius - other.celsius) <= 1.0;
}
~~~

Mảnh mã trên giả định có lớp `Temperature` và trường `celsius`; đây không phải lớp hoàn chỉnh để biên dịch độc lập. Kể cả khi viết một `hashCode()` trả cùng hằng số cho mọi đối tượng, việc vi phạm tính bắc cầu **vẫn còn nguyên**. Cố tìm công thức hash không thể sửa một quan hệ không hợp lệ.

Ngưỡng còn có thể phụ thuộc người dùng, phép đo, màn hình hoặc thời điểm. Nếu lấy một ngưỡng thay đổi theo ngữ cảnh để cài đặt `equals()`, cùng cặp đối tượng có thể lúc được xem bằng nhau, lúc không, ngay cả khi bản thân đối tượng không đổi. Điều này cũng trái kỳ vọng về tính nhất quán của `equals()`.

## 3. Thiết kế đúng: `equals()` diễn đạt danh tính; API riêng diễn đạt độ gần

Giả sử mỗi lần đọc cảm biến có một **mã lần đọc** (`readingId`) duy nhất, cố định. Hai đối tượng cùng mã đại diện cho cùng một lần đọc logic, nên có thể coi là bằng nhau theo danh tính nghiệp vụ. Giá trị nhiệt độ (`celsius`) chỉ dùng để hỏi “hai lần đọc có gần nhau về nhiệt độ không?”.

Thiết kế khi đó có hai phép độc lập:

- `equals(Object)`: so sánh `readingId`, trả lời **“cùng lần đọc?”**; đây là quan hệ tương đương nếu mã ổn định và được gán nhất quán.
- `isCloseTo(Reading other, double tolerance)`: so sánh nhiệt độ trong ngưỡng, trả lời **“hai số đo gần nhau?”**; không tuyên bố hai đối tượng bằng nhau.

Một đối tượng có thể **khác** đối tượng kia theo `equals()`, nhưng **gần** nhau theo `isCloseTo()`. Điều đó không mâu thuẫn: hai phương thức trả lời hai câu hỏi nghiệp vụ khác nhau.

### Ví dụ Java 17 hoàn chỉnh

Tạo tệp **`ApproximateMatchDemo.java`** với nội dung sau:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ApproximateMatchDemo {

    static final class Reading {
        private final String readingId;
        private final double celsius;

        Reading(String readingId, double celsius) {
            this.readingId = Objects.requireNonNull(readingId, "readingId");
            if (!Double.isFinite(celsius)) {
                throw new IllegalArgumentException("celsius must be finite");
            }
            this.celsius = celsius;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Reading other)) {
                return false;
            }
            return readingId.equals(other.readingId);
        }

        @Override
        public int hashCode() {
            return readingId.hashCode();
        }

        public boolean isCloseTo(Reading other, double tolerance) {
            if (!Double.isFinite(tolerance) || tolerance < 0.0) {
                throw new IllegalArgumentException(
                    "tolerance must be finite and >= 0");
            }
            return other != null
                && Math.abs(celsius - other.celsius) <= tolerance;
        }
    }

    public static void main(String[] args) {
        Reading a = new Reading("A", 0.0);
        Reading b = new Reading("B", 0.6);
        Reading c = new Reading("C", 1.2);
        Reading copyOfA = new Reading("A", 0.0);

        double tolerance = 1.0;

        System.out.println("a close b: " + a.isCloseTo(b, tolerance));
        System.out.println("b close c: " + b.isCloseTo(c, tolerance));
        System.out.println("a close c: " + a.isCloseTo(c, tolerance));

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a equals copyOfA: " + a.equals(copyOfA));
        System.out.println("same hash for equal: "
            + (a.hashCode() == copyOfA.hashCode()));
        System.out.println("a close null: " + a.isCloseTo(null, tolerance));

        Set<Reading> readings = new HashSet<>();
        readings.add(a);
        readings.add(b);
        readings.add(c);
        readings.add(copyOfA);
        System.out.println("HashSet size: " + readings.size());
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac ApproximateMatchDemo.java
java ApproximateMatchDemo
~~~

**Kết quả mong đợi:**

~~~text
a close b: true
b close c: true
a close c: false
a equals b: false
a equals copyOfA: true
same hash for equal: true
a close null: false
HashSet size: 3
~~~

Giải thích:

1. Ba lệnh `close` cố ý tái hiện phản ví dụ không bắc cầu. Đây là hành vi **đúng** của phép so khớp gần đúng, vì phương thức này không được dùng làm `equals()`.
2. `a.equals(b)` là `false` vì hai mã lần đọc khác nhau, dù nhiệt độ đủ gần.
3. `a.equals(copyOfA)` là `true` vì chúng mang cùng `readingId`; `hashCode()` dựa trên cùng mã nên tuân thủ quy tắc hash.
4. `isCloseTo(null, tolerance)` chọn trả `false` theo thiết kế API này; `equals(null)` cũng trả `false` theo hợp đồng `Object`.
5. `HashSet` có ba phần tử: `A`, `B`, `C`. Bản sao của `A` không thêm phần tử thứ tư, và ngưỡng so nhiệt độ không ảnh hưởng đến membership.

**Giới hạn có chủ đích:** lớp `Reading` là `final`, các trường là `final` và `readingId` không đổi sau khi tạo. Điều này giúp định nghĩa bằng nhau dựa trên mã ổn định. Quy tắc “cùng `readingId` là cùng một lần đọc logic” chỉ đúng khi hệ thống thực sự bảo đảm ý nghĩa đó; không nên tự áp dụng cùng cách cho mọi mô hình dữ liệu. `isCloseTo` kiểm tra nhiệt độ và ngưỡng đều hữu hạn; nếu ngưỡng âm, `NaN` hoặc vô cực, phương thức ném `IllegalArgumentException`.

## 4. Tác hại của việc nhét phép gần đúng vào `equals()`

### Collection dựa vào hash

`HashSet` và `HashMap` dùng `hashCode()` để xác định vùng tra cứu rồi dùng `equals()` để xác định phần tử hoặc khóa bằng nhau. Nếu `equals()` không có tính bắc cầu, việc coi một giá trị là trùng lặp có thể phụ thuộc các phần tử đã được thêm và thứ tự thao tác. Không còn một cách phân hoạch nhất quán thành những nhóm bằng nhau.

Ví dụ với `a = 0.0`, `b = 0.6`, `c = 1.2`: nếu cho `b` đại diện cả `a` lẫn `c` theo ngưỡng `1.0`, thì `a` và `c` lại không bằng nhau theo cùng quy tắc. Không thể coi “tất cả các giá trị gần nhau” là một khóa hash logic mà vẫn giữ đúng ý nghĩa của phép gần nhau trực tiếp.

**Không đưa quan hệ gần đúng làm khóa đồng nhất của `Map`, điều kiện loại trùng của `Set` hoặc cơ sở cho `hashCode()`.** Hãy lưu đối tượng theo khóa định danh/giá trị chính xác và tìm các đối tượng gần nhau bằng thao tác riêng.

### So sánh để sắp xếp

Tránh viết `Comparator` trả `0` cho hai giá trị chỉ vì chúng cách nhau dưới ngưỡng: một quy tắc kiểu đó thường phá vỡ yêu cầu sắp thứ tự nhất quán. `TreeSet` và `TreeMap` dựa vào kết quả so sánh để xác định thứ tự và việc hai khóa có được coi là tương đương trong cấu trúc cây. Nếu cần sắp xếp, hãy dùng một thứ tự rõ ràng (chẳng hạn `Double.compare` trên số đo hợp lệ), rồi thực hiện tìm kiếm trong khoảng sai số riêng.

### Sai số tương đối và phép so khớp bất đối xứng

Không phải công thức “gần đúng” nào cũng tự động đối xứng. Chẳng hạn `abs(a-b) / abs(a) <= p` phụ thuộc chọn `a` làm mẫu số; đổi chiều hai đối số có thể cho kết quả khác. Cần xác định rõ ý nghĩa của ngưỡng tuyệt đối, ngưỡng tương đối, đơn vị đo và cách xử lý số 0. Ngay cả khi sửa công thức để đối xứng, vấn đề **không bắc cầu** nhìn chung vẫn có thể tồn tại.

## 5. Nếu thật sự cần nhóm bằng nhau theo độ chính xác thì sao?

Có lúc yêu cầu nghiệp vụ thực sự là **xem các giá trị thuộc cùng một mức độ phân giải là bằng nhau**, ví dụ chỉ quan tâm nhiệt độ đã được ghi nhận tới phần mười độ. Khi đó có thể **chuẩn hóa thành một giá trị đại diện ổn định trước khi so sánh**, rồi định nghĩa bằng nhau bằng sự bằng nhau của giá trị đại diện.

Ví dụ minh họa ý tưởng:

~~~java
// Sau khi đã xác thực đầu vào hữu hạn và miền giá trị phù hợp:
long tenthDegrees = Math.round(celsius * 10.0);
~~~

Nếu một kiểu dữ liệu lưu khóa chuẩn hóa `tenthDegrees` và dùng `Long.equals`/so sánh `long` (cùng `hashCode` tương ứng), quan hệ bằng nhau theo khóa **có tính bắc cầu**: cùng khóa thì cùng nhóm. Tuy nhiên, đây là một **quy tắc khác** phép `Math.abs(a - b) <= 0.1`: hai số rất gần nhưng nằm hai phía ranh giới làm tròn có thể khác nhóm, còn hai số cùng nhóm được xem là bằng nhau theo mức phân giải đã chọn. Phải chấp nhận ranh giới này ở cấp yêu cầu nghiệp vụ, không giả vờ hai quy tắc tương đương.

Cách chọn tùy ý nghĩa dữ liệu:

| Yêu cầu thật | Thiết kế phù hợp |
| --- | --- |
| “Cùng một bản ghi/lần đo?” | `equals()` dựa trên ID ổn định của bản ghi |
| “Cùng giá trị đã chuẩn hóa đến độ phân giải cố định?” | Chuẩn hóa rồi so khóa chính xác; đồng bộ `equals()` và `hashCode()` |
| “Hai phép đo cách nhau không quá ε?” | `isCloseTo(other, epsilon)` / `matchesWithinTolerance` |
| “Các điểm đo hình thành nhóm liên thông theo khoảng cách?” | Thuật toán gom cụm/đồ thị riêng, mô tả rõ quy tắc thành viên |
| “Cần tìm mọi giá trị trong khoảng gần X?” | Lọc/tìm trong khoảng theo tiêu chí rõ ràng, không giả lập bằng `equals()` |

Với gom cụm theo quan hệ gần, các phần tử cùng cụm qua chuỗi nối không nhất thiết phải gần nhau trực tiếp. Ví dụ `a` và `c` có thể nằm cùng thành phần liên thông thông qua `b`, dù `a` không gần `c`. Vì thế cần đặt tên và kiểm thử đúng quan hệ mà sản phẩm muốn biểu diễn.

## 6. Checklist thiết kế và kiểm thử

Trước khi định nghĩa `equals()` cho một lớp, hãy tự trả lời:

1. “Bằng nhau” có nghĩa là cùng danh tính, cùng giá trị hay cùng khóa chuẩn hóa? Quy tắc có **phản xạ, đối xứng, bắc cầu** không?
2. Dữ liệu dùng cho `equals()` và `hashCode()` có ổn định trong thời gian đối tượng được dùng làm khóa `HashMap` hoặc phần tử `HashSet` không?
3. Ngưỡng “gần”, đơn vị đo, thuật toán độ tương tự hoặc ý kiến người dùng có đang bị trộn vào `equals()` không? Nếu có, tách thành API chuyên biệt.
4. Với API gần đúng, đã định nghĩa rõ hành vi cho `null`, ngưỡng âm, `NaN`, vô cực, giới hạn sai số và ranh giới chưa?
5. Đã kiểm thử bộ ba `a, b, c` mà `a` gần `b`, `b` gần `c` nhưng `a` không gần `c` chưa? Trường hợp này phải **được phép** ở API gần đúng, nhưng sẽ tố cáo lỗi nếu xảy ra ở `equals()`.

**Kết luận học tập:** `equals()` nói về *quan hệ bằng nhau logic* và phải tuân thủ hợp đồng của `Object`. Một phép so khớp theo ngưỡng có thể rất đúng về nghiệp vụ mà vẫn không phải quan hệ tương đương. Hãy đặt tên riêng cho nó, truyền ngưỡng rõ ràng, kiểm thử các trường hợp biên và giữ `equals()`/`hashCode()` dựa trên định nghĩa bằng nhau ổn định.