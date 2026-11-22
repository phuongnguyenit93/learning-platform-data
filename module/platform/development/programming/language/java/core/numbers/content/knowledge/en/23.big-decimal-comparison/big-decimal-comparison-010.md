# So sánh BigDecimal: không đổi equals toàn hệ thống vì một phép so sánh cụ thể

## 1. Tình huống và nguyên tắc

Trong Java, hai giá trị `BigDecimal` có thể **bằng nhau về số học nhưng không bằng nhau theo `equals`**:

- `new BigDecimal("2.0")` và `new BigDecimal("2.00")` đều biểu diễn số 2, nhưng có `scale()` lần lượt là 1 và 2.
- `a.compareTo(b) == 0` kiểm tra hai số bằng nhau **về giá trị số học**.
- `a.equals(b)` kiểm tra cùng **giá trị số học và scale**. Vì vậy `a.equals(b)` trả `false` cho cặp trên.

Vấn đề thường xuất hiện khi một yêu cầu rất cụ thể, chẳng hạn “so sánh tổng tiền đã tính với tổng tiền người dùng nhập, bỏ qua số lượng số 0 ở cuối”, bị xử lý bằng cách **thay đổi quy tắc equals của cả mô hình, cả ứng dụng hoặc mọi nơi đang dùng BigDecimal**. Đây là giải pháp quá rộng: có thể phá tính nhất quán của `hashCode`, khóa trong collection, quy tắc định danh đối tượng, cache và dữ liệu lưu trữ.

**Nguyên tắc:** đặt chính sách so sánh tại đúng thao tác có nhu cầu đó. Giữ nguyên hợp đồng equality hiện có của các phần còn lại, trừ khi **đặc tả của chính kiểu dữ liệu** yêu cầu một equality mới và bạn kiểm soát đầy đủ các hệ quả.

## 2. Vì sao equals và compareTo khác nhau?

`BigDecimal` lưu một giá trị nguyên chưa scale và một `scale`:

`value = unscaledValue × 10^(-scale)`.

| Biểu diễn | `unscaledValue()` | `scale()` | Giá trị toán học |
|---|---:|---:|---:|
| `2` | 2 | 0 | 2 |
| `2.0` | 20 | 1 | 2 |
| `2.00` | 200 | 2 | 2 |
| `0.00` | 0 | 2 | 0 |

Ví dụ:

~~~java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));     // false
System.out.println(x.compareTo(y));  // 0
System.out.println(x.scale());       // 1
System.out.println(y.scale());       // 2
~~~

`compareTo` trả số âm, 0 hoặc số dương khi giá trị toán học của toán hạng thứ nhất tương ứng nhỏ hơn, bằng hoặc lớn hơn toán hạng thứ hai. **Không kiểm tra `compareTo(...) == -1` hay `== 1`**, vì hợp đồng chỉ bảo đảm dấu của kết quả. Để kiểm tra bằng nhau về số học, dùng `compareTo(...) == 0`.

`equals` của `BigDecimal` xét cả giá trị và scale; `hashCode` tương thích với cách hiểu này, nên hai số bằng nhau về toán học nhưng khác scale thường có hash khác nhau. `BigDecimal` là lớp `final`: không thể subclass để override `equals` của chính `BigDecimal`. Tuy nhiên, vẫn có thể vô tình thay đổi equality của **wrapper, record, entity** hoặc ép normalize BigDecimal trên toàn hệ thống chỉ nhằm sửa một so sánh.

Phân biệt các hợp đồng:

- **Bằng nhau về số học:** `a.compareTo(b) == 0`.
- **Bằng nhau theo biểu diễn BigDecimal:** `a.equals(b)`.
- **Bằng nhau theo nghiệp vụ:** có thể còn yêu cầu **loại tiền, trạng thái, đơn vị, thời điểm, định danh** hoặc những trường khác. Chỉ kiểm tra amount bằng số học chưa chắc xác định được hai đối tượng nghiệp vụ là một.

## 3. Ví dụ chạy được: tác động tới HashSet, TreeSet, HashMap và TreeMap

Lưu chương trình sau trong `BigDecimalEqualityDemo.java` (Java 17+):

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");

        System.out.println("HashMap get(b): " + hashMap.get(b));
        System.out.println("TreeMap get(b): " + treeMap.get(b));
        System.out.println("local numeric equality: "
                + (a.compareTo(b) == 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
~~~

Stdout:

~~~text
equals: false
compareTo: 0
HashSet size: 2
TreeSet size: 1
HashMap get(b): null
TreeMap get(b): first
local numeric equality: true
~~~

**Giải thích:**

- `HashSet` và `HashMap` dựa trên `equals`/`hashCode`. Khóa `2.0` **khác** khóa `2.00` theo quy tắc BigDecimal.
- `TreeSet` và `TreeMap` sử dụng thứ tự tự nhiên từ `compareTo` (hoặc `Comparator` đã cấp). `compareTo` coi hai biểu diễn là một vị trí trong cấu trúc sắp xếp; khóa thứ hai có thể được xem như trùng khóa thứ nhất.
- Chính tài liệu Java mô tả thứ tự tự nhiên của `BigDecimal` **không nhất quán với equals**. `TreeSet` với hai giá trị này xử lý theo quy tắc thứ tự của nó; không nên tự giả định cùng một khái niệm “trùng” giữa mọi collection.

Các thao tác dựa trên `equals` như `List.contains`, `List.remove`, `Stream.distinct`, `HashMap.get` hoặc `Collectors.groupingBy` (với `HashMap` mặc định) có thể hành xử khác `TreeSet` hoặc `TreeMap`. Hãy chọn cấu trúc và hàm so sánh theo yêu cầu, không sửa equality ở toàn bộ hệ thống để che giấu khác biệt.

## 4. Cách đúng khi chỉ cần một phép so sánh số học

Giả sử kiểm tra “giá trị người dùng gửi có bằng tổng tính được về mặt số học không?”. Việc người dùng nhập `100.0` hay `100.00` không ảnh hưởng kết quả xác nhận. So sánh trực tiếp tại vị trí cần kiểm tra:

~~~java
BigDecimal calculated = new BigDecimal("100.00");
BigDecimal entered = new BigDecimal("100.0");

boolean matches = calculated.compareTo(entered) == 0;
System.out.println(matches); // true
~~~

Không cần sửa model, equals, hashCode hay quy tắc chuẩn hóa đầu vào chung.

Nếu thao tác đó được dùng ở một số vị trí có cùng nghĩa, gom thành hàm đặt tên cụ thể:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class AmountComparisons {
    private AmountComparisons() {}

    public static boolean sameNumericValue(BigDecimal left, BigDecimal right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) == 0;
    }
}
~~~

Đoạn trên là **utility class**, không tự chạy vì không có `main`; có thể biên dịch riêng bằng `javac AmountComparisons.java` hoặc gọi từ code khác. Quyết định xử lý `null` là một phần của contract: bản này từ chối `null` để không âm thầm coi “thiếu giá trị” bằng 0. Nếu cần `null == null` theo nghĩa “cùng vắng mặt”, hãy xây dựng hàm riêng có tên và kiểm thử rõ ràng. Không dùng `Objects.equals(left, right)` như một cách thay thế âm thầm vì nó quay lại `BigDecimal.equals`.

**Giới hạn của hàm này:** nó chỉ so sánh hai con số. Nếu là tiền, phải xác thực đơn vị tiền. `100 USD` không đồng nghĩa `100 EUR` chỉ vì hai amount bằng 100.

### Không dùng ==, không dùng toString, không chuyển qua double

- `a == b` chỉ kiểm tra **cùng tham chiếu** đối tượng `BigDecimal`, không phải giá trị.
- `a.toString().equals(b.toString())` so sánh chuỗi biểu diễn, không phù hợp cho equality số học.
- `a.doubleValue() == b.doubleValue()` có thể mất precision hoặc tràn sang vô cực, khiến những giá trị `BigDecimal` thực sự khác nhau bị coi là bằng nhau.
- `a.subtract(b).abs().compareTo(epsilon) <= 0` là **so sánh với dung sai**, một đặc tả khác, không phải equality BigDecimal. Dung sai phải có đơn vị và lý do kinh doanh/kỹ thuật rõ ràng.

## 5. Tại sao không nên override equals của wrapper hoặc entity để sửa một nhu cầu?

Hãy xem model có identity ổn định:

~~~java
record InvoiceLine(String lineId, BigDecimal amount) {}
~~~

Đây là record Java 17; equality sinh tự động từ **cả** `lineId` và `amount`, trong đó amount dùng `BigDecimal.equals`. Nếu có một màn hình cần so sánh riêng **số tiền bỏ qua scale**, đừng vội override `InvoiceLine.equals` chỉ vì màn hình đó. Làm như vậy đổi ý nghĩa của “hai dòng hóa đơn bằng nhau” trong toàn chương trình, trong khi hai dòng vẫn có thể có id khác nhau, thuế suất khác nhau hoặc là các nghiệp vụ khác nhau.

Hậu quả phổ biến của thay đổi equality toàn cục:

1. **Hash contract:** nếu `equals` đã đổi thì `hashCode` phải đổi tương ứng; mọi đối tượng được coi là bằng nhau phải có cùng hash. Chỉ đổi một phương thức là lỗi hợp đồng.
2. **Dữ liệu đang làm khóa:** `HashSet`/`HashMap` có thể mất khả năng tìm khóa hoặc thay đổi logic trùng lặp. Nếu equality hoặc các trường tham gia hash thay đổi **sau khi đưa khóa vào HashMap**, tra cứu có thể thất bại.
3. **Cache, nhóm và distinct:** đối tượng trước kia khác nhau nay bị gộp, làm mất kết quả hay sai số lượng phần tử.
4. **Identity và persistence:** entity có quy tắc định danh/lifecycle riêng; đổi equals chỉ vì scale của một amount có thể ảnh hưởng việc xử lý entity chưa có id, entity đã lưu, collection quan hệ hoặc caching. Cách implement tùy công nghệ; phải đánh giá trên contract của entity.
5. **API và kiểm thử:** equality là hợp đồng được nhiều nơi dựa vào. Thay đổi nó có thể gây regression dù phép so sánh đầu tiên đã “đúng”.

Ngược lại, có những **value object được thiết kế từ đầu** với equality theo giá trị đã chuẩn hóa; đó là quyết định thuộc *kiểu giá trị* và có thể hợp lý. Nhưng cần có đặc tả rõ, đồng bộ `equals`/`hashCode`, xác định cách canonicalize dữ liệu, cùng kiểm thử ở mọi nơi sử dụng. Đừng áp dụng quy tắc đó lên mọi class chỉ vì một màn hình.

## 6. Khi nào normalize có ý nghĩa? Khi nào dễ gây hậu quả?

Hai kỹ thuật thường gặp:

### 6.1. Loại bỏ số 0 cuối bằng stripTrailingZeros

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.stripTrailingZeros().equals(b.stripTrailingZeros())); // true
System.out.println(new BigDecimal("1000.00").stripTrailingZeros());        // 1E+3
~~~

`stripTrailingZeros()` trả BigDecimal khác có thể có **scale âm** và chuỗi khoa học (`1E+3`), đặc biệt khi số là lũy thừa 10. Kết quả có thể hợp lý cho một **canonical key riêng** nhưng không tự động thích hợp cho định dạng, serializing, validation hay báo cáo kế toán vốn cần thể hiện scale. Nếu mục tiêu chỉ là kiểm tra hai con số bằng nhau, `compareTo(...) == 0` rõ nghĩa hơn và tránh biến đổi dữ liệu.

Một giá trị `0.00` sau strip trailing zeros có thể trở thành zero scale 0; điều đó càng nhắc rằng normalize có thể xóa thông tin về biểu diễn ban đầu.

### 6.2. Chốt scale khi kiểu dữ liệu *thực sự* có bất biến scale

Ví dụ một loại số tiền nội bộ **được định nghĩa rõ** là luôn có hai chữ số thập phân, và đầu vào không được làm tròn ngầm:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record FixedTwoDecimalAmount(BigDecimal value) {
    public FixedTwoDecimalAmount {
        Objects.requireNonNull(value, "value");
        value = value.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Đây là **value object dùng trong một miền có scale cố định**, không phải chính sách cho mọi loại tiền. Java record tự sinh `equals`/`hashCode` từ thành phần `value` **sau khi đã normalize trong constructor**. Kết quả `new FixedTwoDecimalAmount(new BigDecimal("2.0"))` và phiên bản `2.00` bằng nhau; đầu vào `2.001` sẽ ném `ArithmeticException` vì đòi làm tròn mà chính sách cấm.

Không sử dụng `setScale(2, HALF_UP)` ở constructor một cách tùy tiện, vì nó tự thay đổi giá trị đầu vào. Nếu cần chấp nhận rồi làm tròn, đó phải là rule rõ trong đặc tả và tên phương thức tạo. Các loại tiền khác nhau có thể sử dụng số chữ số thập phân khác 2; không suy luận bất biến từ thói quen hiển thị.

### Quyết định đặt normalize ở đâu

Nếu bạn **chỉ cần một lần đối chiếu**, gọi `compareTo` ngay trong nghiệp vụ. Nếu loại dữ liệu có bất biến scale ổn định, normalize tại biên tạo **kiểu dữ liệu đó** sau khi thống nhất nghiệp vụ. Nếu dữ liệu làm khóa hash cần canonicalization, chuẩn hóa **khi tạo khóa** và không thay đổi khóa sau khi đưa vào map/set. Không “dọn sạch số 0” khi đọc/ghi khắp hệ thống chỉ để làm cho một phép `equals` tình cờ thành true.

## 7. Collection, comparator và tính nhất quán với equals

`Comparator<BigDecimal> numericOrder = BigDecimal::compareTo;` có thể dùng rõ ràng khi bộ sưu tập cần **thứ tự số học**. Trong sorted collection, comparator trả 0 làm hai phần tử được xem là cùng khóa, kể cả khi `equals` trả false.

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

Comparator<BigDecimal> numericOrder = BigDecimal::compareTo;
Set<BigDecimal> uniqueNumericValues = new TreeSet<>(numericOrder);
uniqueNumericValues.add(new BigDecimal("2.0"));
uniqueNumericValues.add(new BigDecimal("2.00"));
System.out.println(uniqueNumericValues.size()); // 1
~~~

Đây là **đoạn minh họa đặt trong thân phương thức** (không phải chương trình standalone); đã khai báo đầy đủ import dùng trong đoạn. Lưu ý `TreeSet` và `TreeMap` bỏ/gộp phần tử khi comparator trả 0. Nếu giữ nhiều bản biểu diễn để phục vụ báo cáo/audit, việc dùng comparator này để “deduplicate” có thể mất dữ liệu. Nếu cần giữ cả hai và vẫn sắp xếp theo giá trị, dùng collection phù hợp hoặc comparator có **tie-breaker theo scale** để phân biệt hai bản biểu diễn — chọn theo đúng semantics mong muốn.

Đừng thay toàn bộ collection thành `TreeSet` chỉ để workaround equality ở một bước. Khi cần giữ nguyên `HashMap`, có thể dùng khóa chuẩn hóa cục bộ được tài liệu hóa; nhưng chú ý giá trị gốc, scale, null, currency và cách hash/serialize. Đừng lạm dụng `stripTrailingZeros` khi `compareTo == 0` cho phép giải quyết nhu cầu một cách trực tiếp.

### Phân biệt equality với “gần bằng nhau”

Ví dụ dung sai 0.10: `0.00` gần `0.09`, `0.09` gần `0.18`, nhưng `0.00` không gần `0.18`. Quan hệ gần bằng nhau kiểu này **không có tính bắc cầu** nên không thích hợp để trở thành `equals` hoặc comparator mà một sorted collection dùng làm quan hệ trùng khóa. Nếu bài toán cần chấp nhận sai lệch, hãy viết predicate cục bộ với ngưỡng cụ thể, không thay equality và không đưa comparator gần đúng vào `TreeSet`/`TreeMap` một cách mù quáng.

## 8. Cách quyết định theo tình huống

| Yêu cầu | Cách thực hiện phù hợp | Điều cần tránh |
|---|---|---|
| Kiểm tra hai BigDecimal bằng nhau về giá trị số | `a.compareTo(b) == 0` ngay tại vị trí kiểm tra | Override equals của model chỉ vì một dòng if |
| Kiểm tra scale/biểu diễn chính xác như dữ liệu gốc | `a.equals(b)` hoặc kiểm tra cả giá trị và `scale()` | Dùng compareTo rồi bỏ qua yêu cầu scale |
| Kiểm tra số tiền giao dịch | Kiểm tra currency, amount, và rule nghiệp vụ liên quan | Chỉ so sánh amount rồi coi hai giao dịch giống hệt |
| Sắp xếp theo trị số | `Comparator<BigDecimal>` hoặc `compareTo` | Giả định comparator trùng với equals |
| Loại trùng số học cho một báo cáo | Dùng cấu trúc/khóa canonical riêng với nghĩa trùng được mô tả | Áp dụng normalize toàn database hoặc toàn model |
| Kiểu amount bất biến scale | Chốt scale khi tạo value object theo domain contract | Rải `setScale` ở mọi nơi |
| Kiểm tra sai lệch trong phạm vi dung sai | Predicate `abs(a-b) <= tolerance`, quy định cả đơn vị | Sử dụng quan hệ gần bằng như equals/hash/comparator |
| Entity cần so sánh identity | Dựa vào hợp đồng identity của entity, xét lifecycle | Lấy phép so sánh amount để thay định danh entity |

Các lựa chọn này độc lập về mặt **ý nghĩa**. Một hệ thống có thể đồng thời dùng `equals` cho khóa định danh, `compareTo` cho một phép đối soát, comparator cho thứ tự hiển thị và canonical value object cho một nghiệp vụ riêng.

## 9. Thiết kế test bảo vệ cả hành vi mong muốn lẫn hệ quả phụ

Trong đơn vị có phép đối soát theo số học, kiểm thử cả hai hướng:

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

if (a.compareTo(b) != 0) {
    throw new AssertionError("Numeric value should match");
}
if (a.equals(b)) {
    throw new AssertionError("BigDecimal representation unexpectedly matched");
}
~~~

Đoạn này là **code assertion đặt trong method**, không chứa `main`; ghép vào unit test phù hợp.

Kiểm thử bổ sung:

1. **Cặp khác scale:** `2.0` và `2.00` bằng số học, khác về `equals`; `2.00` và `2.01` phải khác về số học.
2. **Số âm và zero:** `-0.00` và `0.0` có giá trị số bằng nhau; so sánh scale vẫn khác. `-2.0` và `-2.00` cũng bằng nhau theo `compareTo`.
3. **Null:** quy định ném lỗi, coi là vắng dữ liệu hay bỏ qua so sánh. Không cho null bị hiểu nhầm là zero.
4. **Hash contract của model:** nếu thiết kế kiểu mới có custom equality, kiểm tra tính phản xạ, đối xứng, bắc cầu, nhất quán và `equals ⇒ cùng hashCode`; thử thao tác `HashSet` và `HashMap`.
5. **Collection theo comparator:** thử số lượng phần tử, `contains`, put/get khi trùng compareTo nhưng khác equals; xác nhận hệ thống có thực sự muốn mất bản biểu diễn hay không.
6. **Giao dịch nhiều tiền tệ:** số tiền cùng amount nhưng khác currency không được coi là cùng giá trị tiền trong domain.
7. **Regression:** khi chỉ sửa một phép so sánh, kiểm thử rằng equality/identity ở cache, mapping và các nghiệp vụ còn lại vẫn tuân theo hợp đồng hiện có.

Khi cần một hàm so sánh riêng, đặt tên phản ánh **nghĩa nghiệp vụ**, ví dụ `sameNumericTotal` hay `matchesEnteredAmount`; tránh một helper chung tên mơ hồ như `isEqual` rồi bị dùng trong mọi ngữ cảnh.

## 10. Những sai lầm dễ mắc

- **“equals sai nên sửa nó”:** thường chỉ là bạn đang cần equality số học tại một vị trí, còn `BigDecimal.equals` đang thực hiện đúng hợp đồng của nó.
- **Override equals ở entity để một phép so sánh amount thành true:** đổi luôn định nghĩa “cùng entity” trên toàn ứng dụng.
- **Sửa equals mà quên hashCode:** vi phạm hợp đồng collection và dễ tạo lỗi khó tái hiện.
- **Sử dụng BigDecimal làm khóa mutable:** `BigDecimal` bất biến, nhưng **wrapper chứa khóa hoặc các trường tham gia equality/hash** có thể bị sửa sau khi insert; đó mới là rủi ro.
- **Thay HashSet bằng TreeSet và giả định hành vi vẫn tương đương:** natural ordering của BigDecimal không nhất quán với equals, dẫn đến số phần tử/khóa khác.
- **Chuẩn hóa bằng stripTrailingZeros ở mọi layer:** có thể đổi scale và chuỗi hiển thị, như `1000.00 → 1E+3`.
- **Chỉ dùng compareTo mà bỏ qua currency:** equality về amount không đồng nghĩa equality về tiền.
- **Dùng double cho so sánh:** có thể mất thông tin chính xác vốn được giữ trong BigDecimal.
- **Dùng tolerance như equality:** quan hệ gần bằng có thể không bắc cầu; không phù hợp để làm hợp đồng set/map.
- **Dùng equals để kiểm tra “đã thanh toán đủ” nhưng người dùng nhập khác scale:** chọn `compareTo == 0` cho phép đối soát được đặc tả là bằng nhau về số học.

## 11. Bài tập củng cố

**Bài 1.** Với `new BigDecimal("0.00")` và `BigDecimal.ZERO`, hãy dự đoán `equals`, `compareTo`, số phần tử của `HashSet`/`TreeSet` sau khi thêm cả hai. Giải thích dựa trên scale.

**Bài 2.** Một API nhận số lượng hàng `"5.0"`, dữ liệu đã tính là `"5"`. Nghiệp vụ chỉ cần kiểm tra cùng số lượng. Chọn cách so sánh và xử lý null; có cần sửa equals của DTO không?

**Bài 3.** Một màn hình lịch sử giao dịch phải giữ nguyên cả số nhập gốc và số đã định dạng. Nếu dùng `stripTrailingZeros` ngay khi đọc database, thông tin nào có thể mất?

**Bài 4.** Viết test chứng minh quan hệ “chênh lệch tuyệt đối không quá 0.10” không bắc cầu với bộ `0.00`, `0.09`, `0.18`. Vì sao không nên dùng quan hệ đó cho `Comparator` của `TreeSet`?

**Gợi ý đáp án:** (1) `equals=false`, `compareTo=0`, HashSet có 2, TreeSet có 1. (2) dùng `compareTo == 0` trong validator có xử lý null rõ; không cần sửa equals DTO. (3) scale và biểu diễn số 0 cuối, thậm chí dạng số mũ. (4) A gần B, B gần C, nhưng A không gần C; sự không bắc cầu phá giả định của thứ tự toàn phần khi sorted collection gom khóa.

## Tài liệu chuẩn

- Java SE 17 — `BigDecimal` (`equals`, `compareTo`, `hashCode`, `stripTrailingZeros`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17 — `Comparable`, quy tắc “consistent with equals”: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html
- Java SE 17 — `TreeSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html
- Java SE 17 — `Object.equals` và `hashCode`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html

**Ghi nhớ:** một nhu cầu so sánh theo *giá trị số học* nên được thể hiện trực tiếp bằng `compareTo(...) == 0` tại đúng chỗ. Việc thay đổi `equals` của model/value object chỉ hợp lý khi **toàn bộ định nghĩa của kiểu đó** thực sự yêu cầu như vậy và hợp đồng `hashCode`, collection, identity cùng dữ liệu được xem xét đầy đủ.
