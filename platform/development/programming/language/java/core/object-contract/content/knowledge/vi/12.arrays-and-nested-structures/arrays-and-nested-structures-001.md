# `equals()` và `hashCode()` của mảng mặc định dựa trên danh tính

## 1. Mục tiêu: mảng có dữ liệu giống nhau chưa chắc “bằng nhau”

Trong Java, **mảng (array) là đối tượng**, kể cả mảng của kiểu nguyên thủy như `int[]`, `double[]`. Nhưng mảng **không ghi đè** `Object.equals(Object)` hoặc `Object.hashCode()` để so sánh các phần tử. Theo mặc định, mảng dùng quy tắc **danh tính đối tượng** (object identity):

- `arrayA.equals(arrayB)` là `true` khi `arrayA` và `arrayB` trỏ đến **chính cùng một mảng**, không phải chỉ vì hai mảng có các phần tử giống nhau.
- `arrayA == arrayB` cũng kiểm tra cùng tham chiếu đối với hai biến kiểu mảng.
- `arrayA.hashCode()` là mã băm theo danh tính mặc định của đối tượng, **không dựa trên nội dung các phần tử**. Không được suy ra nó là địa chỉ bộ nhớ, hay mỗi mảng chắc chắn có hash khác mọi mảng khác.
- Muốn so sánh hoặc băm **theo nội dung**, cần chọn API của `java.util.Arrays` phù hợp với mảng một chiều hay mảng lồng nhau; hoặc thiết kế lớp bao (value object) với `equals`/`hashCode` rõ ràng.

Ví dụ độc lập về ngữ nghĩa:

```java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};
int[] alias = first;

System.out.println(first == second);        // false
System.out.println(first.equals(second));   // false
System.out.println(first == alias);         // true
System.out.println(first.equals(alias));    // true
```

Đây là đoạn mã minh họa (đặt trong một phương thức khi chạy), chưa phải chương trình độc lập. `first` và `second` là **hai đối tượng mảng** riêng biệt; `alias` chỉ tham chiếu lại mảng `first`.

Ngược lại, `Arrays.equals(first, second)` là `true` vì hai mảng `int[]` có các phần tử tương ứng bằng nhau. Hai quan hệ này trả lời **hai câu hỏi khác nhau**: có phải cùng đối tượng không, và nội dung có tương đương không.

## 2. Vì sao `Object.equals` và `Object.hashCode` hoạt động theo danh tính với mảng?

Java quy định mọi kiểu mảng đều là kiểu tham chiếu, kế thừa hành vi thích hợp từ `Object`. Bản thân mảng cung cấp độ dài `length` và các phần tử truy cập bằng chỉ số, nhưng không có một `equals` hay `hashCode` tự sinh theo nội dung như nhiều lớp giá trị.

Nếu một lớp thông thường không ghi đè `equals`, `Object.equals` mặc định so sánh danh tính: `this == other`. Đối với mảng cũng vậy. `Object.hashCode` cho mã băm mặc định tương ứng với danh tính đối tượng. Hai lần gọi trên **cùng một mảng**, khi không có yếu tố bất thường ngoài hợp đồng, trả về cùng mã băm trong một lần chạy.

Điều cần nhớ:

1. **Cùng tham chiếu ⇒ `equals` đúng và hash giống nhau.** Một mảng vẫn là chính nó ngay cả khi các phần tử thay đổi.
2. **Khác tham chiếu ⇒ `array1.equals(array2)` sai**, kể cả khi chúng có các phần tử và độ dài bằng nhau.
3. **Mã băm trùng nhau không chứng minh cùng đối tượng.** `hashCode` trả về `int` nên các đối tượng khác nhau có thể va chạm.
4. **Thay đổi phần tử không chuyển `array.hashCode()` sang “băm nội dung”.** Nó vẫn theo danh tính; trong khi `Arrays.hashCode(array)` lại được tính từ các phần tử hiện tại.
5. `System.identityHashCode(array)` trả mã băm danh tính mặc định của đối tượng, ngay cả khi đối tượng thuộc lớp khác đã ghi đè `hashCode`. Vì mảng không ghi đè phương thức đó, `array.hashCode() == System.identityHashCode(array)`.

Đừng nhầm “identity hash” với ID duy nhất hay địa chỉ trong heap. Hợp đồng Java **không cam kết** mã băm duy nhất trên mọi đối tượng và không cam kết giá trị của mã băm mặc định có thể dùng để nhận dạng đối tượng qua các lần chạy ứng dụng.

## 3. So nội dung một chiều: chuyển từ identity sang `Arrays.equals`

Khi mục tiêu là **dữ liệu** chứ không phải chính đối tượng mảng, dùng `java.util.Arrays` thay cho `array.equals(...)`. Thứ tự, độ dài và quy tắc bằng nhau của từng phần tử vẫn được tôn trọng:

| Dữ liệu và mục đích | So sánh | Băm tương ứng |
| --- | --- | --- |
| Cùng đối tượng mảng | `a == b` hoặc `a.equals(b)` nếu a không null | `a.hashCode()` (identity) |
| Hai `int[]`, `byte[]`, `double[]` theo nội dung | `Arrays.equals(a, b)` đúng overload | `Arrays.hashCode(a)` |
| Hai `String[]` hoặc `Object[]` so từng phần tử | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| Hai `int[][]` hoặc `Object[]` có mảng con, muốn so cả tầng trong | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |

```java
import java.util.Arrays;
// Bên trong main hoặc một phương thức:
int[] first = {1, 2};
int[] second = {1, 2};
System.out.println(first.equals(second));         // false: khác identity
System.out.println(Arrays.equals(first, second)); // true: cùng nội dung
System.out.println(Arrays.hashCode(first)
        == Arrays.hashCode(second));               // true
```

`Arrays.equals` và `Arrays.hashCode` cho mảng phẳng là **cặp nhất quán**: nếu hai mảng bằng nhau theo phép so nội dung thì hai mã băm nội dung phải bằng nhau; chiều ngược lại không đúng do hash collision. Các overload xử lý mảng `null` có kiểu rõ ràng: hai mảng `null` bằng nhau, còn `null` khác mảng rỗng. Đối với `float[]`/`double[]`, phương thức phân biệt `+0.0` với `-0.0`, và coi các giá trị NaN là bằng nhau theo quy tắc của `Float`/`Double`, khác toán tử `==` của primitive. Bài *Arrays.equals() và Arrays.hashCode() cho mảng một chiều* là nơi giải thích chi tiết overload, công thức hash, ví dụ chạy và các biên này.

## 4. Vì sao mảng lồng cần so và băm sâu?

`int[][]` là mảng có phần tử trực tiếp là các `int[]`. Khi dùng `Arrays.equals(int[][], int[][])`, các mảng con riêng biệt được so theo `Object.equals` của **từng mảng con**, không theo số bên trong. Cặp `Arrays.deepEquals`/`Arrays.deepHashCode` đi qua các mảng con để so/băm nội dung đúng mức:

```java
// Trong một phương thức có import java.util.Arrays:
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};
System.out.println(Arrays.equals(a, b));     // false: mảng con khác identity
System.out.println(Arrays.deepEquals(a, b)); // true: cùng giá trị ở các tầng
```

Hai phương thức `deep*` nhận mảng ngoài có kiểu `Object[]` (ví dụ `int[][]`), nên **không gọi trực tiếp** `Arrays.deepEquals(int[], int[])`. Chúng xử lý mảng nguyên thủy ở tầng con bằng overload phù hợp, giữ thứ tự, phân biệt loại mảng, null và độ sâu; không tự đi vào các trường của mọi object tùy ý. Mảng `Object[]` tự chứa chính nó, trực tiếp hoặc gián tiếp, nằm ngoài phạm vi hành vi được xác định của `deepEquals/deepHashCode`: cần thuật toán chu trình riêng. Bài *Arrays.deepEquals() và Arrays.deepHashCode() cho mảng lồng* phân tích sâu các trường hợp, còn bài *Giới hạn khi cấu trúc có tham chiếu vòng* xử lý giới hạn này.

## 5. Đừng nhầm phép so nội dung với hành vi của hash collection

`HashMap` và `HashSet` luôn dùng `equals/hashCode` của **đối tượng khóa/phần tử** được lưu. Với `int[]` trần, chúng dùng identity, không tự gọi `Arrays.equals/hashCode`. Nếu muốn hai mảng mới tạo có cùng phần tử biểu diễn cùng khóa, cần **value object** với `equals` dựa trên `Arrays.equals`, `hashCode` dựa trên `Arrays.hashCode`, cùng bản sao phòng vệ của mảng mutable.

Nếu chính sách là so nội dung mảng lồng, dùng cả cặp `Arrays.deepEquals`/`Arrays.deepHashCode` và sao chép đủ các hàng/phần tử có thể sửa. `final` chỉ giữ tham chiếu không bị gán lại, **không đóng băng mảng**. Bài *Trường mảng trong lớp tự viết và yêu cầu đồng bộ equals() với hashCode()* đi sâu vào trường hợp nhiều trường và cách kết hợp hash.

## 6. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây so sánh danh tính mảng, nội dung mảng một chiều, cấu trúc lồng nhau và tác động khi đưa mảng trực tiếp vào `HashSet`/`HashMap`. Cuối cùng là một **value object bất biến** dùng bản sao của mảng để có `equals`/`hashCode` dựa theo nội dung.

Lưu thành tệp `ArrayIdentityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ArrayIdentityDemo {
    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] input) {
            Objects.requireNonNull(input, "input");
            this.values = input.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof IntArrayKey that
                        && Arrays.equals(values, that.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        int[] alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("same identity hash: "
                + (a.hashCode() == System.identityHashCode(a)));
        System.out.println("Arrays.equals(a, b): " + Arrays.equals(a, b));
        System.out.println("content hash equal: "
                + (Arrays.hashCode(a) == Arrays.hashCode(b)));

        Set<int[]> arrays = new HashSet<>();
        arrays.add(a);
        arrays.add(b);
        arrays.add(alias);
        System.out.println("HashSet<int[]> size: " + arrays.size());
        System.out.println("contains new equal-content array: "
                + arrays.contains(new int[] {1, 2, 3}));

        Map<int[], String> map = new HashMap<>();
        map.put(a, "value-a");
        System.out.println("get same reference: " + map.get(alias));
        System.out.println("get equal-content new reference: " + map.get(b));

        Object[] nestedA = {
                new int[] {1, 2},
                new String[] {"x", "y"}
        };
        Object[] nestedB = {
                new int[] {1, 2},
                new String[] {"x", "y"}
        };
        System.out.println("nested Arrays.equals: "
                + Arrays.equals(nestedA, nestedB));
        System.out.println("nested Arrays.deepEquals: "
                + Arrays.deepEquals(nestedA, nestedB));
        System.out.println("nested deepHashCode equal: "
                + (Arrays.deepHashCode(nestedA)
                   == Arrays.deepHashCode(nestedB)));

        IntArrayKey k1 = new IntArrayKey(a);
        IntArrayKey k2 = new IntArrayKey(b);
        Set<IntArrayKey> keys = new HashSet<>();
        keys.add(k1);
        System.out.println("value key equals: " + k1.equals(k2));
        System.out.println("value key found: " + keys.contains(k2));

        a[0] = 99;
        System.out.println("source a now equals b by content: "
                + Arrays.equals(a, b));
        System.out.println("snapshot key still found: "
                + keys.contains(k2));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 ArrayIdentityDemo.java
java ArrayIdentityDemo
```

Đầu ra kỳ vọng:

```text
a == b: false
a.equals(b): false
a == alias: true
same identity hash: true
Arrays.equals(a, b): true
content hash equal: true
HashSet<int[]> size: 2
contains new equal-content array: false
get same reference: value-a
get equal-content new reference: null
nested Arrays.equals: false
nested Arrays.deepEquals: true
nested deepHashCode equal: true
value key equals: true
value key found: true
source a now equals b by content: false
snapshot key still found: true
```

### Phân tích kết quả

**Mảng gốc khác nhau:** `a` và `b` là hai mảng, mặc dù có cùng chuỗi phần tử `1, 2, 3`. Vì mảng không ghi đè `equals`, `a.equals(b)` trả về `false`. `alias` trỏ đến `a` nên hai biểu thức `a == alias` và `a.equals(alias)` đều đúng.

**Hai loại hash:** `a.hashCode()` là mã băm mặc định theo danh tính, bằng `System.identityHashCode(a)`. `Arrays.hashCode(a)` là mã băm nội dung; với `a` và `b` có cùng nội dung, kết quả nội dung hash bằng nhau. Đừng thử suy từ việc hai hash danh tính khác/giống nhau để quyết định dữ liệu có bằng nhau.

**Collection băm:** `HashSet<int[]>` sử dụng `hashCode`/`equals` của chính đối tượng mảng, nên `a` và `b` được lưu như **hai khóa/phần tử khác nhau**. Thêm `alias` không tăng kích thước vì nó trỏ lại `a`. Một mảng mới có cùng các số cũng không được tìm thấy. Tương tự, `HashMap.get(alias)` tìm được giá trị `value-a`, còn `get(b)` trả về `null` dù `b` chứa cùng số.

**Cấu trúc lồng:** `Arrays.equals(nestedA, nestedB)` trả về `false` vì hai mảng `int[]` bên trong khác tham chiếu. `Arrays.deepEquals` đi vào mảng con và xác nhận dữ liệu tương ứng bằng nhau; `deepHashCode` của hai cấu trúc cũng khớp.

**Value object:** `IntArrayKey` sao chép mảng đầu vào ngay trong constructor, giữ bản sao ở trường `private final` và không để lộ mảng nội bộ ra bên ngoài. `equals`/`hashCode` đều dùng nội dung `values`, nên `k1` và `k2` bằng nhau và tìm thấy trong `HashSet`. Sau khi sửa `a[0]` từ `1` thành `99`, khóa `k1` đã tạo vẫn chứa bản sao gốc; tra cứu bằng `k2` tiếp tục thành công.

Mã này dùng `hashCode` mặc định của mảng **và** `Arrays.hashCode` để minh họa hai ý nghĩa; không in một giá trị số cố định cho mã băm danh tính, vì giá trị ấy có thể thay đổi theo lần chạy.

## 7. Dùng mảng làm khóa `HashMap` hoặc phần tử `HashSet`

Cần chọn xem khóa đại diện cho **danh tính của một vùng dữ liệu mảng** hay **giá trị các phần tử**.

### Khi cần danh tính mảng

Nếu nghiệp vụ muốn hai mảng khác nhau luôn là hai khóa riêng, kể cả khi chứa cùng phần tử, `HashMap<int[], V>` hoặc `HashSet<int[]>` có thể phản ánh yêu cầu ấy. Điều này thường xuất hiện khi theo dõi chính **đối tượng mảng cụ thể** trong bộ nhớ.

Tuy nhiên phải công bố rõ kỳ vọng: tra cứu bằng một mảng **mới được tạo từ cùng phần tử** sẽ không khớp với mảng cũ. Việc này không phải lỗi của collection.

Nếu cần cấu trúc chuyên dùng để kiểm tra danh tính khóa khi các lớp khóa khác có `equals` theo giá trị, Java còn có `IdentityHashMap`; nhưng với mảng, bản thân `equals` đã theo danh tính. `IdentityHashMap` có semantics riêng và chỉ nên chọn khi chủ ý dùng tham chiếu để nhận dạng khóa.

### Khi cần giá trị nội dung mảng

Nếu hai mảng `{1, 2, 3}` phải được coi là cùng khóa logic, **không dùng trần `int[]` làm khóa với kỳ vọng `HashMap` sẽ gọi `Arrays.equals`**. Cần một lớp bao như `IntArrayKey` trong ví dụ: cài đặt `equals` bằng `Arrays.equals`, cài đặt `hashCode` bằng `Arrays.hashCode`, và bảo vệ tính bất biến.

Có thể dùng cấu trúc bất biến khác với hợp đồng bằng nhau theo phần tử, chẳng hạn một danh sách bất biến chứa các giá trị đã được sao chép. Nhưng cần hiểu đúng kiểu phần tử; một `List<int[]>` vẫn mang các phần tử là mảng và phép so sánh phần tử có thể tiếp tục dựa trên danh tính mảng con.

### Nếu mảng đã thay đổi sau khi đưa vào map thì sao?

Có hai trường hợp cần phân biệt:

- **Khóa là `int[]` trần:** sửa phần tử không thay đổi `equals`/`hashCode` danh tính mặc định của mảng. Với cùng tham chiếu khóa, tra cứu bằng nó vẫn giữ quan hệ danh tính thông thường. Tuy vậy nếu nghiệp vụ kỳ vọng so nội dung thì thiết kế đã không phù hợp từ đầu.
- **Khóa là wrapper so nội dung nhưng giữ tham chiếu mảng mutable:** sửa phần tử có thể khiến `hashCode` thay đổi trong khi khóa vẫn nằm ở nhóm băm xác định bởi hash cũ. `get`/`contains` có thể không tìm thấy khóa. Đây là lỗi thiết kế phổ biến.

Vì vậy wrapper dùng cho khóa băm nên **sao chép dữ liệu đầu vào** và nếu có phương thức lấy dữ liệu ra cũng trả về **bản sao phòng vệ** (defensive copy), thay vì để bên ngoài thay đổi dữ liệu mà `equals`/`hashCode` sử dụng. `private final int[] values` tự nó **chỉ cố định tham chiếu tới mảng**, không làm cho phần tử mảng bất biến.

## 8. Phân biệt các API theo nhu cầu

| Nhu cầu cụ thể | API / thiết kế phù hợp | Điều cần tránh |
| --- | --- | --- |
| Hỏi hai biến có trỏ cùng một mảng không | `a == b`, hoặc `a.equals(b)` khi `a` chắc chắn khác `null` | Dùng `Arrays.equals` nếu yêu cầu là danh tính. |
| So hai mảng `int[]` theo phần tử | `Arrays.equals(a, b)` | Dùng `a.equals(b)` rồi suy ra nội dung khác nhau. |
| Tạo hash tương ứng cho `int[]` theo nội dung | `Arrays.hashCode(a)` | Dùng `a.hashCode()` làm fingerprint nội dung. |
| So hai `String[]` theo các chuỗi phần tử | `Arrays.equals(a, b)` | Quên rằng mỗi phần tử tham chiếu dùng `equals` riêng của lớp đó. |
| So hai mảng đa chiều/lồng theo nội dung | `Arrays.deepEquals(a, b)` khi gốc là `Object[]` | Gọi `Arrays.equals` ở cấp ngoài rồi tưởng đi sâu mọi tầng. |
| Tạo hash cho mảng lồng tương ứng | `Arrays.deepHashCode(a)` | Kết hợp `deepEquals` với `Arrays.hashCode` nông nếu dùng làm hợp đồng value object. |
| Dùng nội dung mảng làm khóa băm | Value object sao chép mảng, cặp `Arrays.equals`/`Arrays.hashCode` hoặc deep tương ứng | Dùng `int[]` trần rồi kỳ vọng collection nhận cùng giá trị. |
| Kiểm tra hai mảng có giống nhau khi một/both có thể `null` | `Arrays.equals`, hoặc `Arrays.deepEquals` với mảng lồng phù hợp | Gọi `a.equals(b)` trên `a == null`. |

Ngoài `equals`, lớp tiện ích `Arrays` còn có `mismatch` để tìm vị trí khác đầu tiên của hai mảng và `compare` để so thứ tự từ điển theo overload tương ứng. Đây là các câu hỏi khác với hợp đồng bằng nhau của đối tượng mảng; chỉ dùng khi việc xác định vị trí khác hoặc thứ tự so sánh có giá trị cho bài toán.

## 9. Các lỗi dễ mắc khi làm việc với mảng và cấu trúc lồng

### Lỗi 1: So mảng bằng `equals` và kết luận dữ liệu khác

`new int[]{1,2}.equals(new int[]{1,2})` là `false`, vì hai đối tượng mảng khác nhau. Nếu muốn biết nội dung `int[]` có bằng nhau, phải dùng `Arrays.equals`.

### Lỗi 2: Thấy hash của hai mảng giống nhau rồi xem chúng bằng nhau

Không có hàm hash nào dạng `int` đảm bảo duy nhất cho mọi mảng khả dĩ. Cùng hash có thể là **va chạm**, cả với hash danh tính lẫn hash nội dung. So sánh chính xác bằng API bằng nhau phù hợp, thay vì thay `equals` bằng `hashCode()==hashCode()`.

### Lỗi 3: Dùng `Arrays.equals` cho `int[][]`

`int[][]` là mảng chứa các mảng `int[]`. `Arrays.equals` cấp ngoài chỉ so từng mảng con theo `equals` của chúng, dẫn tới trả `false` cho hai cấu trúc mới nhưng có cùng ma trận số. Muốn đi sâu, dùng `Arrays.deepEquals`; khi băm nội dung cho wrapper tương ứng, dùng `Arrays.deepHashCode`.

### Lỗi 4: Dùng `Arrays.deepEquals` mà không xem xét vòng tham chiếu

Nếu `Object[]` chứa chính nó hoặc các mảng tạo thành chu trình, thuật toán deep không phải giải pháp so sánh đồ thị có chu trình. Tránh thiết kế dữ liệu có vòng trong phạm vi dùng `deepEquals`/`deepHashCode`, hoặc cài thuật toán so sánh với theo dõi nút đã duyệt và hợp đồng riêng.

### Lỗi 5: Chỉ ghi đè `equals` của wrapper

Nếu wrapper định nghĩa bằng nhau theo `Arrays.equals(values, other.values)` nhưng không ghi đè `hashCode` tương ứng, hai wrapper có nội dung bằng nhau có thể nhận hash mặc định khác nhau và không thể dùng làm khóa băm một cách đáng tin cậy. Cần cả `Arrays.hashCode(values)` cho mảng một chiều, hoặc cặp deep tương ứng khi chính sách là so nội dung mảng lồng.

### Lỗi 6: Sao chép bề mặt rồi tưởng đã bất biến sâu

`array.clone()` sao chép **mảng ngoài**, nhưng với `Object[]` chứa các mảng con hay đối tượng mutable, các phần tử được sao chép dưới dạng tham chiếu. Bên ngoài vẫn có thể sửa những mảng con. Nếu wrapper muốn làm khóa băm **theo toàn cấu trúc lồng**, phải cân nhắc sao chép sâu phù hợp với miền dữ liệu, đảm bảo từng thành phần tham gia bằng nhau/hash không thể bị thay đổi từ ngoài.

### Lỗi 7: Dùng `Arrays.toString` làm chuỗi khóa rồi băm

`Arrays.toString(int[])` hữu ích khi hiển thị, nhưng với `Object[]` lồng mảng, kết quả có thể chứa chuỗi mô tả danh tính phần tử mảng con. Dùng `Arrays.deepToString` để hiển thị mảng lồng thông thường khi cần, song **chuỗi hiển thị không phải định dạng serialization hay canonical identity chuẩn** cho mọi kiểu phần tử. Không biến đầu ra debug thành quy tắc danh tính mà chưa đặc tả.

## 10. Checklist kiểm thử

Khi làm việc với các lớp bao mảng hoặc các cấu trúc lưu trữ mảng, nên kiểm tra:

1. Hai mảng **khác tham chiếu, cùng phần tử**: `a.equals(b)` sai, `Arrays.equals(a,b)` đúng.
2. Hai biến trỏ **cùng mảng**: so danh tính đúng, kể cả khi sửa phần tử.
3. Hai mảng **khác độ dài** hoặc khác ít nhất một phần tử: `Arrays.equals` sai.
4. `null`: `Arrays.equals(null, null)` với overload xác định trả đúng; gọi phương thức trên tham chiếu `null` gây lỗi.
5. Mảng tham chiếu có phần tử `null`: `Arrays.equals(Object[], Object[])` cần cho kết quả đúng theo từng vị trí.
6. Hai mảng lồng với **các mảng con riêng** nhưng cùng nội dung: `Arrays.equals` cấp ngoài sai, `Arrays.deepEquals` đúng.
7. Nếu dùng so nội dung, mọi cặp bằng nhau phải cho cùng `Arrays.hashCode`/`Arrays.deepHashCode` tương ứng; hash bằng nhau **không suy ra** bằng nhau.
8. Với `HashMap`/`HashSet`: xác định rõ muốn dùng danh tính mảng hay giá trị phần tử; test cả trường hợp truy vấn bằng mảng mới có cùng phần tử.
9. Với wrapper bất biến: sửa mảng gốc sau khi tạo khóa, và sửa bản sao nếu có API xuất dữ liệu, phải **không làm đổi** kết quả `equals`/`hashCode` của khóa đã lưu.
10. Với cấu trúc lồng: xác định rõ có chứa chu trình, các đối tượng mutable, và cần so sánh nông hay sâu.

## 11. Tổng kết

Mảng Java dùng `equals()` và `hashCode()` mặc định dựa trên **danh tính đối tượng**, nên hai mảng được tạo riêng có cùng phần tử vẫn không bằng nhau theo `array1.equals(array2)`. Khi bài toán cần **ngữ nghĩa nội dung**, `Arrays.equals`/`Arrays.hashCode` là cặp tương ứng cho mảng một chiều; `Arrays.deepEquals`/`Arrays.deepHashCode` xử lý mảng tham chiếu lồng nhau không có chu trình theo cách thích hợp. Nếu mảng dùng làm khóa trong collection băm mà cần so nội dung, hãy đưa nó vào một **value object bảo vệ tính bất biến**, thiết kế `equals` và `hashCode` cùng tiêu chí. Sự phân biệt giữa danh tính, nội dung, so sánh nông và so sánh sâu quyết định tính đúng đắn của mọi thao tác tra cứu.