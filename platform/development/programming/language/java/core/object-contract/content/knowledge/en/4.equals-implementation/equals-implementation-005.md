# So sánh trường nguyên thủy và trường tham chiếu khi cài đặt `equals`

Khi tự cài đặt `equals(Object)` cho một lớp Java, phần cốt lõi là **so sánh những trường quyết định hai đối tượng có cùng giá trị theo bài toán hay không**. Cách so sánh phụ thuộc vào kiểu của trường:

- Với **kiểu nguyên thủy** như `int`, `long`, `boolean`, thường dùng `==` để so sánh trực tiếp giá trị. `float` và `double` cần quyết định rõ cách xử lý `NaN` và dấu của số không.
- Với **kiểu tham chiếu** như `String`, lớp tự định nghĩa, danh sách hay mảng, `==` kiểm tra hai tham chiếu có trỏ tới cùng một đối tượng; muốn so sánh **giá trị/nội dung**, phải dùng phép so sánh phù hợp với kiểu đó.
- `equals` của lớp chứa nhiều trường thường kết hợp các phép so sánh trên, đồng thời phải triển khai `hashCode` nhất quán.

Ví dụ, hai đối tượng `UserProfile` độc lập có cùng `age = 20` và `displayName = "Lan"` có thể được xem là bằng nhau. So sánh `age` bằng `==` là đúng vì đó là `int`; so sánh `displayName` bằng `==` lại có thể sai vì đó là `String`, và hai chuỗi nội dung giống nhau vẫn có thể là hai đối tượng khác nhau.

## 1. Trường nguyên thủy: so sánh giá trị

Các kiểu nguyên thủy Java gồm `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`. Giá trị của chúng nằm trực tiếp trong trường; không có tham chiếu tới đối tượng riêng cho giá trị nguyên thủy đó.

| Kiểu trường | Cách so sánh khi triển khai `equals` | Điều cần biết |
| --- | --- | --- |
| `byte`, `short`, `int`, `long` | `a == b` | So sánh giá trị số; không có khái niệm hai instance của một `int`. |
| `char` | `a == b` | So sánh giá trị `char` (đơn vị mã UTF-16), không phải so sánh văn bản đã chuẩn hóa. |
| `boolean` | `a == b` | Cùng `true` hoặc cùng `false` thì bằng nhau. |
| `float` | Thường dùng `Float.compare(a, b) == 0` | Phân biệt `+0.0f` với `-0.0f`; xem các `NaN` là bằng nhau trong quy tắc của `Float`. |
| `double` | Thường dùng `Double.compare(a, b) == 0` | Có cùng quy tắc đặc biệt với `double`; dễ đồng bộ với `Double.hashCode`. |

Đối với `float`/`double`, **`==` không sai về cú pháp**, nhưng nghĩa khác `Float.compare`/`Double.compare`:

~~~java
System.out.println(0.0 == -0.0);                         // true
System.out.println(Double.compare(0.0, -0.0) == 0);      // false
System.out.println(Double.NaN == Double.NaN);           // false
System.out.println(Double.compare(Double.NaN, Double.NaN) == 0); // true
~~~

Nếu lớp được thiết kế theo cách so sánh của `Double`, dùng `Double.compare` trong `equals` và `Double.hashCode` (hoặc `Objects.hash` có đóng hộp `double`) trong `hashCode`. Điều này đặc biệt hợp lý nếu muốn `equals` nhất quán với `Double.equals`.

**Không dùng `Math.abs(a - b) < epsilon` tùy ý làm định nghĩa `equals` tổng quát:** quan hệ “chênh lệch nhỏ hơn ngưỡng” thường không có tính bắc cầu. Chẳng hạn khi ngưỡng là `0.1`, `0.00` gần `0.06`, `0.06` gần `0.12`, nhưng `0.00` không gần `0.12`. Điều này vi phạm hợp đồng `equals`. Dùng dung sai trong phép kiểm tra số thực riêng biệt khi phù hợp, thay vì tự động áp nó vào `Object.equals`.

## 2. Trường tham chiếu: phải hiểu `equals` của kiểu trường

Một trường kiểu `String`, `Integer`, `Address` hay `List<String>` giữ **tham chiếu** (hoặc `null`). Trong `equals`:

- `a == b` là `true` nếu cùng tham chiếu hoặc cả hai đều `null`. Nó không kiểm tra nội dung của hai đối tượng khác nhau.
- `a.equals(b)` gọi phương thức `equals` của đối tượng bên trái, nhưng ném `NullPointerException` nếu `a == null`.
- `Objects.equals(a, b)` trả `true` khi cả hai `null`, trả `false` khi đúng một bên `null`, và khi cả hai khác `null` sẽ gọi `a.equals(b)`. Đây là lựa chọn tiện lợi, an toàn với `null` cho đa số trường tham chiếu có ngữ nghĩa `equals` phù hợp.

Ví dụ trực tiếp:

~~~java
String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);                   // false
System.out.println(first.equals(second));              // true
System.out.println(java.util.Objects.equals(first, second)); // true
System.out.println(java.util.Objects.equals(null, null));     // true
System.out.println(java.util.Objects.equals(first, null));    // false
~~~

Hai lệnh `new String(...)` trong ví dụ chủ động tạo hai đối tượng chuỗi độc lập để làm rõ khác biệt. Trong chương trình thông thường, không cần tạo `new String` từ literal chỉ để so sánh.

**`Objects.equals` không tự tạo “so sánh sâu”.** Nó chỉ ủy quyền cho `equals` của kiểu trường. Nếu kiểu đó kế thừa `Object.equals` mà không override, kết quả vẫn phản ánh danh tính. Ví dụ một lớp `Address` không override `equals` có thể khiến hai địa chỉ chứa các trường giống hệt nhau bị coi là khác nhau.

### Chọn phép so sánh đúng cho từng kiểu tham chiếu

| Kiểu trường | Cách so sánh thường phù hợp trong `equals` của lớp chứa |
| --- | --- |
| `String` | `Objects.equals(name, that.name)` để so sánh chính xác nội dung và xử lý `null`. |
| Lớp giá trị tự định nghĩa | `Objects.equals(address, that.address)`, **sau khi** `Address.equals` đã được định nghĩa đúng. |
| `Integer`, `Long`, `Boolean` (wrapper) | `Objects.equals(boxed, that.boxed)` hoặc kiểm tra giá trị phù hợp; tránh `==` giữa hai wrapper vì cache/boxing có thể làm kết quả khó hiểu. |
| `List` | `Objects.equals(list, that.list)`, nếu ngữ nghĩa danh sách là so phần tử cùng thứ tự. |
| `Set` | `Objects.equals(set, that.set)`, nếu muốn so tập phần tử, không phụ thuộc thứ tự duyệt. |
| `Map` | `Objects.equals(map, that.map)`, nếu muốn so các ánh xạ key-value tương ứng. |
| Enum | `status == that.status` là thích hợp vì mỗi hằng enum là một instance duy nhất. |
| Mảng nguyên thủy, ví dụ `int[]` | `Arrays.equals(a, b)` để so từng phần tử. |
| Mảng đối tượng một chiều, ví dụ `String[]` | `Arrays.equals(a, b)` để so các phần tử bằng `Objects.equals`. |
| Mảng lồng nhau, ví dụ `int[][]` | `Arrays.deepEquals(a, b)` nếu cần so nội dung các mảng con thay vì danh tính của từng mảng con. |

Các so sánh theo `List`, `Set` và `Map` chỉ đúng khi **hợp đồng của phần tử/key/value** cũng đúng. Nếu phần tử là lớp không override `equals`, một collection có nội dung “trông như nhau” vẫn có thể không `equals`.

### Riêng đối với mảng

Mảng Java kế thừa `Object.equals` và **không override `equals` để so từng phần tử**. Vì thế:

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a == b);                       // false
System.out.println(a.equals(b));                  // false
System.out.println(java.util.Objects.equals(a,b)); // false
System.out.println(java.util.Arrays.equals(a,b));  // true
~~~

`Arrays.equals` xử lý cả hai mảng `null`; nếu hai mảng có cùng độ dài và từng phần tử tương ứng bằng nhau, kết quả `true`. Đối với mảng chứa mảng, `Arrays.equals` chỉ so các phần tử mảng bên trong theo tham chiếu; `Arrays.deepEquals` có thể đi sâu vào mảng con. Nếu chọn `Arrays.deepEquals`, phần `hashCode` tương ứng thường phải dùng `Arrays.deepHashCode`. Với `Arrays.equals` một chiều, dùng `Arrays.hashCode`.

Cần hiểu giới hạn: `Arrays.deepEquals` dành cho cây mảng thông thường; mảng có tham chiếu vòng trở lại chính nó không phải tình huống cần trông đợi phép duyệt sâu hoạt động an toàn.

## 3. Ví dụ Java 17+: kết hợp nhiều kiểu trường trong `equals`

Giả sử hai kế hoạch học tập có cùng `level`, `active`, `rating`, `title`, danh sách chủ đề và các mốc tiến độ thì được xem là cùng giá trị. Các trường là dữ liệu của **value object**; đây không phải quy tắc so sánh danh tính thực thể trong mọi hệ thống.

Tệp **`CoursePlanEqualsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class CoursePlanEqualsDemo {

    static final class CoursePlan {
        private final int level;
        private final boolean active;
        private final double rating;
        private final String title;
        private final int[] checkpoints;
        private final List<String> topics;

        CoursePlan(int level, boolean active, double rating,
                   String title, int[] checkpoints, List<String> topics) {
            this.level = level;
            this.active = active;
            this.rating = rating;
            this.title = title; // Cho phép null; String bất biến.
            this.checkpoints = Arrays.copyOf(
                Objects.requireNonNull(checkpoints), checkpoints.length
            );
            this.topics = List.copyOf(Objects.requireNonNull(topics));
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CoursePlan that)) {
                return false;
            }
            return level == that.level
                && active == that.active
                && Double.compare(rating, that.rating) == 0
                && Objects.equals(title, that.title)
                && Arrays.equals(checkpoints, that.checkpoints)
                && Objects.equals(topics, that.topics);
        }

        @Override
        public int hashCode() {
            int result = Objects.hash(level, active, rating, title, topics);
            result = 31 * result + Arrays.hashCode(checkpoints);
            return result;
        }
    }

    public static void main(String[] args) {
        CoursePlan first = new CoursePlan(
            2, true, 4.5, new String("Objects"),
            new int[] {1, 3}, List.of("java", "junit")
        );
        CoursePlan second = new CoursePlan(
            2, true, 4.5, new String("Objects"),
            new int[] {1, 3}, List.of("java", "junit")
        );
        CoursePlan changed = new CoursePlan(
            2, true, 4.5, "Objects",
            new int[] {1, 4}, List.of("java", "junit")
        );

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first.equals(changed));
        System.out.println(first.equals(null));
        System.out.println(Objects.equals(null, null));

        Set<CoursePlan> plans = new HashSet<>();
        plans.add(first);
        plans.add(second);
        plans.add(changed);
        System.out.println(plans.size());

        System.out.println(
            Arrays.equals(new int[] {1, 3}, new int[] {1, 3})
        );
        System.out.println(Double.compare(+0.0, -0.0) == 0);
        System.out.println(Double.compare(Double.NaN, Double.NaN) == 0);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CoursePlanEqualsDemo.java
java CoursePlanEqualsDemo
~~~

Kết quả chuẩn:

~~~text
false
true
true
false
false
true
2
true
false
true
~~~

Đối chiếu từng kết quả:

1. `first == second` → `false` vì hai lời gọi constructor tạo **hai `CoursePlan` độc lập**.
2. `first.equals(second)` → `true`: các trường nguyên thủy bằng nhau; `String` có cùng nội dung; hai mảng khác instance nhưng có phần tử giống nhau; hai danh sách có phần tử cùng thứ tự.
3. Hash của hai `CoursePlan` bằng nhau vì `hashCode` dùng cùng dữ liệu làm cơ sở mà `equals` sử dụng.
4. `first.equals(changed)` → `false` vì `checkpoints` khác ở phần tử thứ hai (`3` so với `4`).
5. `first.equals(null)` → `false` theo hợp đồng `equals`.
6. `Objects.equals(null, null)` → `true`.
7. `HashSet` có kích thước `2`: `first` và `second` được coi là cùng giá trị; `changed` là giá trị khác.
8. Hai mảng `int[]` độc lập có cùng phần tử nên `Arrays.equals` trả `true`.
9. `Double.compare(+0.0, -0.0) == 0` → `false`.
10. `Double.compare(Double.NaN, Double.NaN) == 0` → `true`.

Trong constructor, `Arrays.copyOf` sao chép mảng do người gọi đưa vào để họ không thể thay đổi nội dung trường qua tham chiếu mảng gốc. `List.copyOf` lưu danh sách không thể chỉnh sửa bằng thao tác thay đổi phần tử của danh sách. Vì danh sách ví dụ chỉ chứa `String` bất biến, thiết kế này phù hợp làm đối tượng giá trị ổn định. `List.copyOf` không cho các phần tử `null`; đây là ràng buộc được chọn cho ví dụ, không phải quy tắc bắt buộc của `equals`.

Tại sao `hashCode` có hai phần? `Objects.hash(...)` xử lý các trường nguyên thủy qua boxing và các trường tham chiếu qua mã băm của chúng; tuy nhiên, **mảng cần dùng `Arrays.hashCode`** để hash nội dung từng phần tử. Kết hợp bằng `31 * result + ...` để tất cả thành phần quyết định `equals` cũng đóng góp vào kết quả hash.

## 4. Quy tắc nhất quán giữa `equals` và `hashCode`

Hợp đồng `equals` yêu cầu tính phản xạ, đối xứng, bắc cầu, nhất quán (khi dữ liệu liên quan không đổi) và `x.equals(null) == false` với `x != null`.

Hợp đồng `hashCode` yêu cầu:

> Nếu `x.equals(y)` là `true`, thì **`x.hashCode() == y.hashCode()` phải là `true`**.

Điều ngược lại không bắt buộc: hai giá trị khác nhau có thể có cùng hash (collision).

Trong ví dụ, `level`, `active`, `rating`, `title`, `checkpoints`, `topics` đều ảnh hưởng tới `equals` và đều được phản ánh trong `hashCode`. Nếu bỏ `checkpoints` khỏi hash nhưng vẫn so trong `equals`, điều đó **không nhất thiết phá vỡ** mệnh đề “bằng nhau thì cùng hash”, nhưng có thể làm tăng collision. Ngược lại, nếu hash thêm một trường không tham gia `equals` và trường đó khác giữa hai đối tượng được coi là bằng nhau, sẽ **vi phạm hợp đồng**.

Để giữ tính ổn định, nên tránh thay đổi các trường tham gia `equals`/`hashCode` khi đối tượng đang là key của `HashMap` hoặc phần tử của `HashSet`. Nếu hash thay đổi sau khi lưu, thao tác tìm kiếm hay xóa có thể thất bại dù tham chiếu vẫn còn trong collection.

## 5. Các lỗi thường gặp và cách sửa

### Lỗi 1: Dùng `==` cho `String` hoặc wrapper

~~~java
// Dễ sai nếu mong so nội dung:
return age == that.age && name == that.name;

// Đúng khi name là String và có thể null:
return age == that.age && Objects.equals(name, that.name);
~~~

`Integer` và các wrapper khác cũng là kiểu tham chiếu. Một số giá trị đóng hộp có thể được tái sử dụng qua cache; điều này không làm `==` thành phép so sánh giá trị đáng tin cậy cho hai wrapper bất kỳ. Dùng `Objects.equals` khi cần so nội dung và xử lý `null`.

### Lỗi 2: Dùng `Objects.equals` cho mảng để mong so phần tử

~~~java
// Sai mục tiêu: đây vẫn là so tham chiếu của hai mảng.
Objects.equals(firstArray, secondArray);

// Đúng với int[] một chiều:
Arrays.equals(firstArray, secondArray);
~~~

Đồng thời, dùng `Arrays.hashCode` tương ứng cho mảng một chiều; với mảng lồng nhau dùng cặp `Arrays.deepEquals` / `Arrays.deepHashCode` khi cần ngữ nghĩa sâu.

### Lỗi 3: Gọi `equals` trên trường có thể null

~~~java
// Có nguy cơ NullPointerException:
title.equals(that.title);

// An toàn khi một hoặc cả hai bên null:
Objects.equals(title, that.title);
~~~

Nếu nghiệp vụ cấm `null`, cũng có thể kiểm tra ngay trong constructor bằng `Objects.requireNonNull(title)` rồi gọi `title.equals(that.title)` sau đó. Cần nhất quán với điều kiện hợp lệ của đối tượng.

### Lỗi 4: So sánh thiếu hoặc thừa trường

Nếu `equals` chỉ so `name` mà hai người trùng tên chưa chắc là cùng người, cách định nghĩa giá trị có thể sai nghiệp vụ. Ngược lại, nếu thêm trường mô tả tạm thời như `lastViewedAt` vào `equals` của một value object vốn chỉ quan tâm `id`, hai giá trị đáng lẽ bằng nhau có thể bị phân biệt không cần thiết.

**Chọn trường theo ý nghĩa của kiểu dữ liệu**, rồi bảo đảm `hashCode` tuân theo cùng quyết định. Việc IDE sinh phương thức tự động chỉ giúp tránh lỗi cú pháp; vẫn phải xem lại lựa chọn trường.

### Lỗi 5: Bỏ qua kiểu con và tính đối xứng

Với lớp có thể được kế thừa, việc lớp cha dùng `instanceof Parent` còn lớp con lại so thêm một trường có thể khiến `parent.equals(child)` khác `child.equals(parent)`. Cần thiết kế chiến lược bình đẳng rõ ràng. Một lựa chọn đơn giản cho **value object** là dùng lớp `final`, như `CoursePlan` ở trên. Nếu lớp buộc phải mở cho kế thừa, hãy cân nhắc kiểm tra `getClass()` hoặc một chiến lược khác, đồng thời kiểm thử tính đối xứng/bắc cầu; không có công thức duy nhất đúng cho mọi mô hình kế thừa.

### Lỗi 6: Hiểu nhầm `BigDecimal`, `String` hoặc collection

`BigDecimal("1.0")` và `BigDecimal("1.00")` có thể tương đương về số học theo `compareTo`, nhưng `equals` trả `false` vì xét cả `scale`. Tương tự, `String.equals` so chính xác chuỗi, kể cả chữ hoa/chữ thường; muốn chuẩn hóa trước so sánh phải đặt ra quy tắc rõ ràng và bảo đảm quy tắc đó cũng áp dụng nhất quán cho hash.

Với các collection, `Objects.equals` dựa vào `equals` của collection và phần tử. `List` giữ ngữ nghĩa thứ tự; `Set` so theo phần tử không phụ thuộc thứ tự duyệt; `Map` so theo ánh xạ key-value. Không được tự động coi mọi collection là các tập hợp phần tử không thứ tự.

## 6. Quy trình viết và kiểm thử `equals`

1. **Xác định ý nghĩa “cùng giá trị”.** Chỉ rõ các trường tham gia so sánh và xem đó là value object hay entity có danh tính riêng.
2. **Kiểm tra cùng tham chiếu:** `if (this == obj) return true;`.
3. **Kiểm tra đối tượng đầu vào:** `null` và kiểu không phù hợp phải cho `false`. Với class `final`, `instanceof YourClass that` là một cách viết rõ ràng trong Java 17.
4. **So sánh từng trường đúng kiểu:** nguyên thủy thường `==`, `float/double` chọn `Float.compare`/`Double.compare`, tham chiếu dùng `Objects.equals` khi hợp lý, mảng dùng `Arrays.equals` hoặc `Arrays.deepEquals`.
5. **Viết `hashCode` tương ứng:** cùng thông tin xác định `equals` phải tạo ra cùng hash; riêng mảng cần `Arrays.hashCode` hoặc `Arrays.deepHashCode`.
6. **Kiểm thử các ca thiết yếu:** cùng tham chiếu, hai instance có cùng dữ liệu, một trường thay đổi, `null`, kiểu không liên quan, chuỗi độc lập có cùng nội dung, mảng độc lập có cùng phần tử, `NaN`/`±0.0` nếu có `float/double`, và lưu/tìm trong `HashSet` hoặc `HashMap`.
7. **Giữ trạng thái so sánh ổn định:** ưu tiên value object bất biến; không để mảng hoặc collection có thể thay đổi nội dung qua alias ngoài ý muốn.

Một `record` Java tự sinh `equals` và `hashCode` dựa trên các thành phần, rất thuận tiện cho nhiều value object. Tuy nhiên, **record chứa mảng không tự so sâu nội dung mảng**; component kiểu mảng vẫn so bằng ngữ nghĩa tham chiếu trong `equals` được sinh. Vì vậy vẫn cần cân nhắc kiểu thành phần trước khi chọn record để đại diện giá trị.

## 7. Tự kiểm tra

1. Một lớp có trường `int age` và `String name`. Vì sao `age == that.age` phù hợp nhưng `name == that.name` không đủ để xác định nội dung bằng nhau?
2. Hai `int[]` độc lập chứa `{1, 2, 3}`. Hãy dự đoán kết quả của `==`, `Objects.equals` và `Arrays.equals`, rồi giải thích.
3. Nếu hai đối tượng bằng nhau theo `equals` nhưng có hash khác nhau, điều gì có thể xảy ra khi đưa chúng vào `HashSet`?
4. Vì sao `Double.compare(+0.0, -0.0)` và phép `+0.0 == -0.0` cho cách nhìn khác nhau về giá trị?
5. Nếu trường `List<Address>` được so bằng `Objects.equals`, lớp `Address` cần có ngữ nghĩa `equals` nào để hai danh sách địa chỉ độc lập có cùng dữ liệu được xem là bằng nhau?

**Ghi nhớ:** Khi triển khai `equals`, hãy so **giá trị nguyên thủy bằng phép so phù hợp với kiểu**, so **trường tham chiếu qua ngữ nghĩa `equals` của đối tượng đó**, và xử lý **mảng riêng bằng các phương thức `Arrays`**. Cùng một tập trường và quy tắc so sánh phải nhất quán với `hashCode`; đó là nền tảng để hai đối tượng độc lập nhưng cùng giá trị hoạt động đúng trong Java collections.