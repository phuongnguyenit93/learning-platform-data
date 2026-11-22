# Comparable và thứ tự tự nhiên

Khi có một danh sách số, “sắp xếp tăng dần” thường đã đủ rõ. Nhưng với đối tượng như một phiên bản phần mềm, hóa đơn hay sản phẩm, chương trình cần biết **đối tượng nào đứng trước đối tượng nào**.

`Comparable<T>` cho phép một kiểu tự khai báo quy tắc so sánh với các đối tượng phù hợp. Quy tắc mặc định đó được gọi là **thứ tự tự nhiên (natural ordering)** của kiểu.

Bài này giải thích ý nghĩa của thứ tự tự nhiên, hợp đồng của `compareTo`, cách tự cài đặt và tác động của quy tắc so sánh đối với collection. Các chương trình hoàn chỉnh dùng API Java 17, đã được biên dịch bằng `--release 17` và chạy để kiểm tra stdout. Các đoạn mã rút gọn còn lại minh họa một thao tác hoặc phần thân phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn cần có khả năng:

- Đọc kết quả âm, bằng không hoặc dương của `compareTo`.
- Giải thích khi nào một kiểu nên có thứ tự tự nhiên.
- Cài đặt so sánh nhiều trường mà không gây tràn số.
- Phân biệt “ngang hàng trong thứ tự” với `equals`.
- Dự đoán ảnh hưởng của `compareTo == 0` tới `TreeSet` và khóa của `TreeMap`.

## 1. Thứ tự tự nhiên giải quyết vấn đề gì?

Giả sử có các phiên bản:

```text
2.0.0
1.10.0
1.2.0
```

Ta muốn so sánh lần lượt phiên bản lớn, phiên bản nhỏ rồi bản vá:

```text
1.2.0 < 1.10.0 < 2.0.0
```

Nếu mỗi nơi sử dụng danh sách đều tự viết lại quy tắc, rất dễ có nơi so đúng theo số, nơi khác chỉ so chuỗi. Một quy tắc gắn với chính kiểu `Version` giúp các thao tác theo thứ tự tự nhiên dùng chung ý nghĩa.

### “Tự nhiên” là quy ước của kiểu

Thứ tự tự nhiên không phải một quy luật duy nhất cho mọi đối tượng:

- `Integer` có thứ tự theo giá trị số.
- `String` có thứ tự từ điển theo đơn vị mã UTF-16.
- Một kiểu phiên bản đơn giản có thể chọn thứ tự theo ba thành phần số.
- Một kiểu sản phẩm có nhiều nhu cầu như theo giá, tên hoặc ngày nhập; chưa chắc có một lựa chọn đủ rõ để làm mặc định.

Vì vậy, đừng thêm `Comparable` chỉ để một lời gọi sắp xếp biên dịch được. Trước hết hãy trả lời: **kiểu này có một quy tắc mặc định ổn định, có ý nghĩa và được các bên sử dụng cùng hiểu không?**

Nếu chỉ cần một cách xếp riêng cho một màn hình, một quy tắc bên ngoài qua `Comparator` thường phù hợp hơn. `Comparator` được nhắc ở đây để phân biệt trách nhiệm; trọng tâm của bài là thứ tự do chính kiểu khai báo.

### So sánh không tự sắp xếp

Gọi:

```java
first.compareTo(second);
```

chỉ trả về kết quả so sánh hai đối tượng. Nó không đổi chỗ chúng và không tự sắp xếp một danh sách.

Thuật toán sắp xếp sẽ gọi quy tắc đó nhiều lần để quyết định thứ tự các phần tử. Các cấu trúc có sắp thứ tự còn dùng quy tắc để tìm vị trí lưu và tra cứu.

## 2. Đọc giao diện Comparable<T>

Dạng rút gọn của giao diện:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

Đây là phần chữ ký minh họa, không phải mã để tự định nghĩa lại giao diện của thư viện chuẩn.

Trong chương trình đầy đủ ở phần sau, kiểu `Version` khai báo `implements Comparable<Version>`.

`Comparable<Version>` nói rằng đối tượng của lớp cung cấp phép so sánh với đối tượng `Version` phù hợp. Khi triển khai thực tế, `compareTo` phải là phương thức `public`.

Nên dùng tham số kiểu cụ thể thay vì triển khai `Comparable` dạng thô. Kiểu cụ thể giúp trình biên dịch kiểm tra việc sử dụng và giảm nhu cầu ép kiểu không an toàn.

### Ý nghĩa giá trị trả về

Với `x.compareTo(y)`:

| Kết quả | Ý nghĩa |
| --- | --- |
| Nhỏ hơn `0` | `x` đứng trước `y` |
| Bằng `0` | `x` và `y` ngang hàng theo quy tắc thứ tự |
| Lớn hơn `0` | `x` đứng sau `y` |

Điều cần dùng là **dấu**, không phải một con số cụ thể.

Cách kiểm tra đúng:

```java
if (x.compareTo(y) < 0) {
    // x đứng trước y.
}
```

Không nên viết điều kiện `x.compareTo(y) == -1` để nhận biết mọi trường hợp “đứng trước”. Một phương thức hợp lệ có thể trả về `-5`, `-32` hoặc một giá trị âm khác.

### Bằng không không có nghĩa cùng đối tượng

Hai đối tượng khác nhau trong bộ nhớ có thể cho `compareTo == 0`. Ý nghĩa trực tiếp là chúng được quy tắc thứ tự xem là tương đương.

Để biết sự tương đương này có trùng với khái niệm bằng nhau của kiểu hay không, cần xét thêm `equals`. Đây là điểm quan trọng khi dùng các tập hợp có sắp thứ tự.

## 3. Những API dùng thứ tự tự nhiên

| API hoặc cấu trúc | Cách dùng thứ tự tự nhiên |
| --- | --- |
| `Collections.sort(list)` | Sắp xếp danh sách theo thứ tự tự nhiên của phần tử |
| `list.sort(null)` | Không truyền comparator riêng; dùng thứ tự tự nhiên |
| `Arrays.sort(objectArray)` | Sắp xếp mảng đối tượng có khả năng so sánh phù hợp |
| `Collections.min(values)`, `Collections.max(values)` | Tìm phần tử nhỏ nhất hoặc lớn nhất theo thứ tự tự nhiên |
| `new TreeSet<E>()` | Tổ chức phần tử bằng thứ tự tự nhiên khi không có comparator riêng |
| `new TreeMap<K, V>()` | Tổ chức khóa theo thứ tự tự nhiên khi không có comparator riêng |

Có hai điều cần phân biệt:

1. Một đối tượng `ArrayList` không tự sắp xếp sau khi `add`. Bạn phải yêu cầu sắp xếp khi cần.
2. Một `TreeSet` duy trì trật tự của các phần tử trong cấu trúc; nó còn dùng kết quả so sánh để xác định phần tử trùng.

`Comparable` áp dụng cho đối tượng. Các overload như `Arrays.sort(int[])` xử lý mảng nguyên thủy bằng hợp đồng riêng; các giá trị `int` không phải đối tượng triển khai `Comparable`.

### Điều kiện sử dụng

- Phần tử hoặc khóa phải so sánh được với nhau theo quy tắc đang dùng.
- Danh sách đem sắp xếp phải hỗ trợ việc thay đổi vị trí phần tử.
- Dữ liệu phải đáp ứng chính sách về `null`.
- `Collections.min` và `max` cần dữ liệu không rỗng; collection rỗng gây `NoSuchElementException`.

Ví dụ, `List.of(...)` không cho phép sửa đổi nên không thể được dùng trực tiếp như danh sách cần sắp xếp tại chỗ. Có thể đưa dữ liệu sang một `ArrayList` trước khi sắp xếp, như chương trình dưới đây.

## 4. Quan sát thứ tự có sẵn của Integer và String

Tạo tệp **`NaturalOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class NaturalOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(10, 2, -3, 2));
        Collections.sort(numbers);
        System.out.println("numbers = " + numbers);
        System.out.println("min = " + Collections.min(numbers));
        System.out.println("max = " + Collections.max(numbers));

        String[] words = {"a", "B", "A", "b", "aa", "a2", "a10"};
        Arrays.sort(words);
        System.out.println("words = " + Arrays.toString(words));
        System.out.println("text 1.10 vs 1.2 = "
                + Integer.signum("1.10".compareTo("1.2")));
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 NaturalOrderDemo.java
java -Dfile.encoding=UTF-8 NaturalOrderDemo
```

Stdout:

```text
numbers = [-3, 2, 2, 10]
min = -3
max = 10
words = [A, B, a, a10, a2, aa, b]
text 1.10 vs 1.2 = -1
```

### Đọc kết quả

- Các số nguyên được xếp theo giá trị số, không phải theo hình thức chuỗi.
- Hai phần tử `2` vẫn còn trong danh sách sau sắp xếp. Sắp xếp danh sách không đồng nghĩa loại trùng.
- Trong thứ tự tự nhiên của `String`, `"A"` và `"B"` đứng trước các chữ thường trong dữ liệu này.
- Khi một chuỗi là tiền tố của chuỗi kia, chuỗi ngắn hơn đứng trước: `"a"` đứng trước `"a10"`.
- `"a10"` đứng trước `"a2"` vì vị trí khác nhau đầu tiên so `'1'` với `'2'`, không phân tích cả dãy thành số.
- Chuỗi `"1.10"` đứng trước `"1.2"`, trong khi phiên bản số `1.10` nên đứng sau `1.2` theo quy tắc phiên bản đã chọn.

Bài dùng `Integer.signum(...)` chỉ để hiển thị dấu bằng `-1`, `0` hoặc `1`. Đây là phép chuẩn hóa kết quả để đọc, không phải yêu cầu mọi `compareTo` đều trả về đúng ba giá trị đó.

Thứ tự tự nhiên của chuỗi không phải quy tắc sắp xếp tên người theo mọi ngôn ngữ. Khi cần quy tắc theo ngôn ngữ hoặc không phân biệt hoa thường, hãy thiết kế chính sách so sánh riêng và kiểm tra các yêu cầu về ký tự.

## 5. Hợp đồng mà compareTo phải tuân thủ

Một lần sắp xếp có thể so một cặp theo nhiều chiều và ở những thời điểm khác nhau. Nếu kết quả mâu thuẫn, cấu trúc hoặc thuật toán không còn có thể dựa vào một quan hệ thứ tự ổn định.

Gọi `sign(v)` là dấu của số nguyên `v`: âm, bằng không hoặc dương.

### 5.1. Đổi chiều phải đổi dấu

Với hai đối tượng hợp lệ:

```text
sign(x.compareTo(y)) == -sign(y.compareTo(x))
```

Nếu `x` đứng trước `y`, thì `y` phải đứng sau `x`. Không được viết quy tắc có thể kết luận mỗi đối tượng đều nhỏ hơn đối tượng kia.

Nên kiểm tra quan hệ qua dấu; không yêu cầu `x.compareTo(y)` luôn bằng đúng số đối của `y.compareTo(x)`.

Một phần của hợp đồng cũng yêu cầu tính đối xứng của khả năng so sánh: nếu so `x` với `y` gây ngoại lệ do chúng không so sánh được, chiều ngược lại cũng không được giả vờ là một phép so sánh hợp lệ.

### 5.2. Có tính bắc cầu

Nếu `x` đứng sau `y` và `y` đứng sau `z`, thì `x` phải đứng sau `z`:

```text
x > y và y > z  =>  x > z
```

Một quy tắc vòng tròn kiểu “A trước B, B trước C, C trước A” không thể làm thứ tự tự nhiên hợp lệ.

### 5.3. Hai đối tượng ngang hàng phải có quan hệ giống nhau với đối tượng thứ ba

Nếu:

```text
x.compareTo(y) == 0
```

thì đối với mọi `z` trong miền so sánh phù hợp:

```text
sign(x.compareTo(z)) == sign(y.compareTo(z))
```

Nếu quy tắc đã coi `x` và `y` là ngang hàng, nó không được cho một đối tượng đứng trước `z` và đối tượng kia đứng sau `z`.

### 5.4. So sánh chính mình cho kết quả bằng không

Với một đối tượng hợp lệ và không thay đổi trạng thái:

```text
x.compareTo(x) == 0
```

Đây là một kiểm tra nhỏ nhưng có ích khi viết kiểu tự định nghĩa.

### 5.5. Quy tắc phải ổn định trong lúc sử dụng

Không nên để kết quả phụ thuộc ngẫu nhiên, thời gian hiện tại hoặc một dữ liệu bên ngoài thay đổi không kiểm soát.

Nếu giá trị tham gia thứ tự có thể đổi, phải có chính sách sử dụng rõ ràng, đặc biệt khi đối tượng đang là phần tử hoặc khóa của một cấu trúc đã sắp thứ tự.

Vi phạm hợp đồng có thể dẫn tới kết quả sắp xếp sai, hành vi cấu trúc dữ liệu không đáng tin hoặc ngoại lệ do thuật toán phát hiện mâu thuẫn. Không phải mọi lỗi hợp đồng đều được Java phát hiện ngay; việc một lần chạy không có lỗi không chứng minh quy tắc đúng.

## 6. Cài đặt thứ tự tự nhiên cho kiểu Version

Ta xây dựng kiểu phiên bản gồm ba số không âm:

```text
major.minor.patch
```

Quy tắc:

1. So `major`.
2. Nếu ngang nhau, so `minor`.
3. Nếu vẫn ngang nhau, so `patch`.

Đây là **so sánh từ điển theo nhiều trường**: dừng tại trường đầu tiên tạo khác biệt. “Từ điển” ở đây mô tả cách ưu tiên từng thành phần; mỗi thành phần vẫn được so theo giá trị số.

Ví dụ:

| Hai phiên bản | Trường quyết định |
| --- | --- |
| `1.99.99` và `2.0.0` | `major` |
| `1.2.9` và `1.10.0` | `minor` |
| `1.2.3` và `1.2.4` | `patch` |
| `1.2.3` và `1.2.3` | Không có khác biệt |

Kiểu ví dụ chỉ biểu diễn bộ ba số. Nó không triển khai toàn bộ quy tắc Semantic Versioning, phần tiền phát hành, metadata hoặc phân tích chuỗi đầu vào.

### Chương trình hoàn chỉnh

Tạo tệp **`VersionComparableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

public class VersionComparableDemo {
    public record Version(int major, int minor, int patch)
            implements Comparable<Version> {
        public Version {
            if (major < 0 || minor < 0 || patch < 0) {
                throw new IllegalArgumentException("Version parts must be non-negative");
            }
        }

        @Override
        public int compareTo(Version other) {
            int result = Integer.compare(major, other.major);
            if (result != 0) {
                return result;
            }

            result = Integer.compare(minor, other.minor);
            if (result != 0) {
                return result;
            }

            return Integer.compare(patch, other.patch);
        }

        @Override
        public String toString() {
            return major + "." + minor + "." + patch;
        }
    }

    public static void main(String[] args) {
        Version first = new Version(1, 2, 0);
        Version same = new Version(1, 2, 0);
        Version later = new Version(1, 10, 0);

        List<Version> versions = new ArrayList<>(List.of(
                new Version(2, 0, 0), later, first, same));
        versions.sort(null);

        System.out.println("sorted = " + versions);
        System.out.println("1.10.0 vs 1.2.0 = "
                + Integer.signum(later.compareTo(first)));
        System.out.println("same compareTo = " + first.compareTo(same));
        System.out.println("same equals = " + first.equals(same));
        System.out.println("set = " + new TreeSet<>(versions));
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 VersionComparableDemo.java
java -Dfile.encoding=UTF-8 VersionComparableDemo
```

Stdout:

```text
sorted = [1.2.0, 1.2.0, 1.10.0, 2.0.0]
1.10.0 vs 1.2.0 = 1
same compareTo = 0
same equals = true
set = [1.2.0, 1.10.0, 2.0.0]
```

### Vì sao cách cài đặt này đúng với mô hình đã chọn?

- `record` cung cấp các thành phần không thể gán lại sau khi tạo, phù hợp với việc giữ ổn định khóa so sánh.
- Hàm tạo từ chối thành phần âm, giữ miền giá trị đúng thiết kế.
- `Integer.compare` so theo số mà không dùng phép trừ có nguy cơ tràn.
- Trường sau chỉ được xét khi trường trước ngang nhau.
- Hai phiên bản trả về `0` khi cả ba thành phần đều bằng nhau.
- `equals` do record sinh cũng xét ba thành phần đó, nên khái niệm bằng nhau và ngang hàng trong thứ tự nhất quán trong ví dụ.
- `toString` chỉ phục vụ hiển thị. Việc sắp xếp không dựa vào chuỗi mà nó trả về.

Danh sách sau sắp xếp giữ cả hai phiên bản `1.2.0`. Khi chuyển sang `TreeSet`, hai phiên bản này trở thành một phần tử vì quy tắc thứ tự coi chúng bằng nhau.

### Tại sao không cộng tất cả thành phần?

Cách lấy tổng `major + minor + patch` làm mất mức ưu tiên. Ví dụ, `1.9.0` và `2.0.0` sẽ bị xếp theo tổng chứ không theo phiên bản lớn trước.

Cách ghép thành `major * 10000 + minor * 100 + patch` cũng đòi hỏi giới hạn chặt về kích thước mỗi thành phần và có thể tràn số. So từng trường giữ đúng ý nghĩa mà không cần mã hóa nhiều trường vào một số.

## 7. Tránh phép trừ và các lỗi dấu

Một cách viết dễ mắc lỗi:

```java
return this.value - other.value;
```

Với số nguyên có phạm vi hữu hạn, phép trừ có thể tràn và cho dấu ngược với quan hệ cần biểu diễn.

Ví dụ:

```text
Integer.MIN_VALUE < 1
```

nhưng phép trừ `Integer.MIN_VALUE - 1` tràn thành một số dương. Quy tắc so sánh như vậy sẽ nói số nhỏ hơn đứng sau số lớn hơn.

Cách viết phù hợp cho trường số nguyên:

```java
return Integer.compare(this.value, other.value);
```

Tương tự, có thể dùng `Long.compare` cho `long` và những hàm so sánh đúng kiểu. Với số dấu phẩy động, cần hiểu cả chính sách đối với giá trị đặc biệt; không áp dụng tùy tiện phép trừ rồi ép sang `int`.

### Không đảo dấu một kết quả tùy ý bằng phép âm

Dùng `-other.compareTo(this)` có thể gặp vấn đề nếu kết quả là `Integer.MIN_VALUE`, vì giá trị đó không có số đối biểu diễn được bằng `int`.

Nếu cần đảo hướng so sánh, hãy sử dụng quy tắc phù hợp như đổi thứ tự đối số ở thao tác so sánh an toàn, hoặc một comparator đảo chiều. Không nên biến một nhu cầu hiển thị giảm dần thành thay đổi tùy tiện của thứ tự tự nhiên.

## 8. Tính nhất quán với equals

Một thứ tự tự nhiên **nhất quán với equals** khi:

```text
x.compareTo(y) == 0  tương đương với  x.equals(y)
```

Đây là khuyến nghị mạnh, dù giao diện `Comparable` có các kiểu thực tế được tài liệu hóa là ngoại lệ.

### Vì sao cần quan tâm?

Các cấu trúc khác nhau xác định sự trùng lặp bằng cơ chế khác nhau:

| Cấu trúc | Cơ chế chính liên quan đến sự bằng nhau |
| --- | --- |
| `HashSet`, khóa của `HashMap` | `equals` cùng hợp đồng `hashCode` |
| `TreeSet`, khóa của `TreeMap` dùng thứ tự tự nhiên | Kết quả của `compareTo` |
| `List` | Cho phép nhiều phần tử; sắp xếp không tự loại các phần tử ngang hàng |

Nếu `compareTo` chỉ xét tuổi của người nhưng `equals` xét mã người dùng, hai người khác nhau cùng tuổi có thể bị một `TreeSet` coi là cùng phần tử.

Giải pháp không phải lúc nào cũng là thêm ngẫu nhiên một trường vào cuối phép so sánh. Trước hết phải xác định **khái niệm bằng nhau của kiểu** và việc dùng tuổi có thực sự là thứ tự tự nhiên hay chỉ là một cách xem dữ liệu.

Nếu muốn nhiều người cùng tuổi vẫn được giữ, lựa chọn có thể là một danh sách được sắp xếp theo tuổi hoặc một quy tắc sắp xếp có tiêu chí phân biệt phù hợp. Cần làm rõ ý nghĩa trước khi chọn cấu trúc.

### Quan hệ với hashCode

`Comparable` không thay thế hợp đồng `equals/hashCode`.

- Nếu tự ghi đè `equals`, cần bảo đảm `hashCode` nhất quán với nó.
- `compareTo == 0` không tự thay đổi giá trị hash.
- Một quy tắc thứ tự hợp lệ về mặt toán học vẫn có thể không nhất quán với `equals`; khi đó việc dùng cấu trúc tập hợp cần được cân nhắc và tài liệu hóa.

## 9. BigDecimal: một ngoại lệ thực tế

`BigDecimal` minh họa rõ hai cách nhìn:

- `compareTo` so giá trị số, nên `4.0` và `4.00` được xem ngang hàng.
- `equals` xét cả biểu diễn thang số (scale), nên hai giá trị đó không bằng nhau theo `equals`.

Đây không phải lỗi của trình sắp xếp. Nó là khác biệt trong hợp đồng bằng nhau và thứ tự của kiểu.

Tạo tệp **`ComparisonPitfallsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparisonPitfallsDemo {
    public static void main(String[] args) {
        int small = Integer.MIN_VALUE;
        int large = 1;

        System.out.println("bad subtraction sign = "
                + Integer.signum(small - large));
        System.out.println("safe comparison sign = "
                + Integer.signum(Integer.compare(small, large)));

        BigDecimal first = new BigDecimal("4.0");
        BigDecimal second = new BigDecimal("4.00");

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(first);
        hashSet.add(second);

        TreeSet<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(first);
        boolean secondAdded = treeSet.add(second);

        TreeMap<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(first, "first");
        treeMap.put(second, "second");

        System.out.println("decimal equals = " + first.equals(second));
        System.out.println("decimal compareTo = " + first.compareTo(second));
        System.out.println("HashSet size = " + hashSet.size());
        System.out.println("TreeSet second added = " + secondAdded);
        System.out.println("TreeSet size = " + treeSet.size());
        System.out.println("TreeMap size = " + treeMap.size());
        System.out.println("TreeMap value = " + treeMap.get(first));
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ComparisonPitfallsDemo.java
java -Dfile.encoding=UTF-8 ComparisonPitfallsDemo
```

Stdout:

```text
bad subtraction sign = 1
safe comparison sign = -1
decimal equals = false
decimal compareTo = 0
HashSet size = 2
TreeSet second added = false
TreeSet size = 1
TreeMap size = 1
TreeMap value = second
```

### Đọc hai nhóm bằng chứng

**Nhóm số nguyên:**

- Phép trừ cho dấu dương sai với quan hệ thực.
- `Integer.compare` cho dấu âm đúng.

**Nhóm BigDecimal:**

- `HashSet` giữ hai phần tử vì chúng khác nhau theo `equals`.
- `TreeSet` không thêm phần tử thứ hai vì phép so sánh trả về `0`.
- `TreeMap` có một khóa theo quy tắc thứ tự; lần `put` thứ hai cập nhật giá trị tương ứng thành `"second"`.

Nếu thiết kế hệ thống dùng số thập phân làm phần tử duy nhất hoặc khóa, cần lựa chọn rõ quan hệ “cùng giá trị” cần áp dụng. Không nên coi `TreeSet` và `HashSet` là hai bản thay thế chỉ khác hiệu năng.

Không có một cách chuẩn hóa biểu diễn phù hợp mọi nghiệp vụ. Nếu hệ thống cần chuẩn hóa scale hoặc dạng biểu diễn, hãy quy định điều đó tại ranh giới dữ liệu thay vì chắp vá sau khi thấy số phần tử bị khác.

## 10. Null, kiểu không phù hợp và dữ liệu khả biến

### Null không có vị trí trong thứ tự tự nhiên của đối tượng

Theo hợp đồng `Comparable`, so một đối tượng hợp lệ với `null` cần gây `NullPointerException`.

Trong ví dụ `Version`, việc truy cập thành phần của `other` khi `other == null` dẫn tới lỗi đó. Nếu cần, có thể kiểm tra tường minh ở đầu phương thức để lỗi được diễn đạt rõ hơn.

Đừng hiểu rằng mọi thao tác sắp xếp có `null` đều luôn báo lỗi: cách thuật toán thực thi còn tùy dữ liệu, chẳng hạn có thể chưa cần so cặp nào. Thiết kế an toàn là loại bỏ/từ chối `null`, hoặc cung cấp chính sách riêng qua comparator khi muốn xếp `null` trước hay sau.

Tương tự, `TreeSet` và `TreeMap` dùng thứ tự tự nhiên không phải nơi phù hợp để lưu `null` như một giá trị khóa có thứ hạng tự nhiên.

### Không so các đối tượng khác miền một cách tùy tiện

Một tập hợp chứa lẫn số nguyên, chuỗi và đối tượng riêng không tự có thứ tự tự nhiên chung.

Generics giúp hạn chế nhiều lỗi khi biên dịch. Dùng kiểu thô rồi trộn các kiểu không so sánh được có thể chỉ đẩy lỗi thành `ClassCastException` lúc chạy.

### Không thay khóa so sánh khi đối tượng đang nằm trong cây

Giả sử một đối tượng được `TreeSet` đặt vào vị trí dựa trên giá trị hiện tại. Nếu bạn sửa trường mà `compareTo` dùng, cấu trúc không tự biết để đưa đối tượng sang vị trí khác.

Hậu quả có thể là:

- Thứ tự duyệt không còn phản ánh giá trị hiện tại.
- Tìm hoặc xóa không hoạt động như bạn dự đoán.
- Ràng buộc về phần tử duy nhất trở nên không đáng tin.

Nên ưu tiên khóa bất biến. Nếu phải đổi, hãy loại bỏ đối tượng bằng trạng thái cũ trước, thực hiện thay đổi rồi thêm lại theo quy tắc của hệ thống. Với dữ liệu đã bị thay đổi sai trong cấu trúc, không nên giả định một lệnh `remove` muộn vẫn chắc chắn tìm đúng.

Danh sách đã sắp xếp cũng không tự sắp lại khi dữ liệu phần tử thay đổi. Tuy không có vị trí cây cần bảo toàn, bạn vẫn phải sắp xếp lại trước khi dựa vào thứ tự mới.

## 11. Phân biệt Comparable với Comparator

| Câu hỏi | `Comparable<T>` | `Comparator<T>` |
| --- | --- | --- |
| Quy tắc nằm ở đâu? | Gắn với chính kiểu đối tượng | Đối tượng quy tắc bên ngoài |
| Phương thức chính | `x.compareTo(y)` | `comparator.compare(x, y)` |
| Vai trò thường dùng | Thứ tự mặc định của kiểu | Các cách xếp theo từng nhu cầu |
| Số chính sách | Một thứ tự tự nhiên được kiểu công bố | Có thể có nhiều chính sách độc lập |
| Có cần sửa lớp đối tượng? | Có, khi tự khai báo triển khai | Không nhất thiết |

Một kiểu có thể triển khai `Comparable` và vẫn được sắp bằng nhiều comparator khác nhau.

Nếu truyền comparator cho một thao tác hoặc cấu trúc, comparator đó quyết định thứ tự trong ngữ cảnh ấy. Việc lớp có `compareTo` không có nghĩa quy tắc tự nhiên luôn được gọi bất kể cấu hình.

Ví dụ `Version` chọn thứ tự số tăng dần làm mặc định. Một màn hình muốn hiển thị mới nhất trước có thể dùng chính sách đảo chiều ở thao tác sắp xếp, giữ nguyên hợp đồng tự nhiên của kiểu.

Khi comparator được dùng cho `TreeSet` hoặc `TreeMap`, kết quả so bằng không của comparator cũng có tác động đến sự duy nhất giống vai trò đã thấy với `compareTo`.

## 12. Quy trình tự thiết kế và kiểm chứng

### Bước 1: viết quy tắc bằng lời

Ví dụ:

> Phiên bản đứng trước nếu thành phần số đầu tiên khác nhau, xét theo thứ tự major, minor, patch, có giá trị nhỏ hơn.

Nếu mô tả còn mơ hồ như “đối tượng quan trọng hơn đứng trước”, cần làm rõ dữ liệu nào thể hiện độ quan trọng và cách phá hòa.

### Bước 2: thống nhất miền dữ liệu và khái niệm bằng nhau

Trả lời:

- Có chấp nhận giá trị thiếu hay `null` không?
- Đối tượng có thể thay đổi sau khi tạo không?
- Hai đối tượng được xem là cùng một giá trị khi nào?
- `compareTo == 0` có trùng với `equals` không?
- Kiểu có được dùng làm khóa hoặc phần tử trong cấu trúc cây không?

### Bước 3: cài đặt từng tiêu chí, không gộp mất ý nghĩa

Dùng thao tác so sánh đúng kiểu; trả về ngay khi tiêu chí ưu tiên tạo khác biệt. Chỉ xét tiếp khi kết quả bằng không.

### Bước 4: kiểm tra dấu và các bộ dữ liệu biên

Một bộ kiểm tra hữu ích cần có:

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Hai giá trị nhỏ/lớn thông thường | Dấu đúng theo mô tả |
| Cùng giá trị nhưng hai đối tượng khác nhau | So bằng không; kiểm tra thêm `equals` |
| Đổi thứ tự hai đối số | Đổi dấu |
| Ba giá trị theo chuỗi tăng | Tính bắc cầu |
| Hai đối tượng ngang hàng, thêm đối tượng thứ ba | Quan hệ với đối tượng thứ ba nhất quán |
| Giá trị sát biên kiểu số | Không sai do tràn |
| Chỉ khác tiêu chí cuối | Không bỏ quên tiêu chí |
| Null hoặc dữ liệu ngoài miền | Hành vi từ chối rõ ràng |

Các kiểm tra trên một số mẫu không chứng minh hợp đồng đúng cho mọi dữ liệu. Chúng là bằng chứng thực thi cần kết hợp với cách lập luận về quy tắc.

### Bước 5: kiểm tra cả nơi sử dụng

- Sắp một danh sách rồi đối chiếu từng cặp kề nhau.
- Thử các phần tử so bằng không để xem danh sách có giữ đủ không.
- Thêm vào `TreeSet` và kiểm tra số phần tử theo quy tắc mong muốn.
- Nếu dùng làm khóa, thử `put` hai khóa ngang hàng trong `TreeMap`.
- Đối chiếu với cấu trúc dựa trên `equals/hashCode` khi cần.

## 13. Lỗi thường gặp và cách sửa

### Chỉ trả về 1 hoặc -1, không có trường hợp bằng không

Điều đó có thể khiến một đối tượng lớn hơn chính nó hoặc hai chiều cùng mang dấu không hợp lệ. Hãy xử lý tiêu chí bằng nhau và trả về `0` khi không còn khác biệt.

### Dùng phép trừ hoặc ép kiểu mất thông tin

Dùng hàm so sánh đúng kiểu thay vì biến hiệu thành kết quả so sánh. Đặc biệt, ép hiệu của `long` xuống `int` có thể làm mất phần dữ liệu quyết định dấu.

### So theo chuỗi hiển thị thay vì ý nghĩa dữ liệu

Chuỗi phiên bản là một ví dụ: `"1.10"` không được so như hai thành phần số. Hãy so dữ liệu cấu trúc nếu đó mới là ý nghĩa nghiệp vụ.

### Chọn một thuộc tính phụ làm toàn bộ thứ tự tự nhiên

Hai người cùng tuổi hoặc hai sản phẩm cùng giá chưa chắc là một giá trị. Trước khi dùng một trường như vậy, kiểm tra tác động tới `equals` và cấu trúc duy nhất.

### Dựa vào thứ tự hiện tại của danh sách

Chỉ số, thứ tự chèn hoặc vị trí trong một danh sách bên ngoài không nên trở thành phụ thuộc biến động của `compareTo`. Quy tắc phải thuộc về giá trị của đối tượng và miền so sánh đã xác định.

### Đánh đồng thứ tự ổn định với loại trùng

Sắp xếp danh sách có tính ổn định giữ thứ tự tương đối của những phần tử so bằng không. Điều đó không biến chúng thành một phần tử duy nhất; `TreeSet` mới áp dụng quy tắc duy nhất theo phép so sánh.

### Cho rằng đã triển khai Comparable thì mọi kiểu con đều tự tương thích

Thiết kế kế thừa và bổ sung tiêu chí ở kiểu con có thể tạo mâu thuẫn với lớp cha. Cần xác định miền đối tượng được so sánh và hợp đồng đối xứng; với kiểu giá trị, mô hình bất biến và giới hạn kế thừa có thể giúp giảm độ phức tạp.

## 14. Thực hành

### Bài 1: dự đoán thứ tự chuỗi

Sửa mảng chuỗi thành:

```text
v2, v10, v1, V2, v01
```

Trước khi chạy, dự đoán thứ tự tự nhiên và giải thích từng vị trí theo ký tự khác nhau đầu tiên. Phân biệt kết quả này với yêu cầu “sắp theo số phiên bản” hoặc “không phân biệt hoa thường”.

### Bài 2: kiểm chứng tiêu chí cuối

Thêm vào danh sách phiên bản:

```text
1.2.9
1.2.1
1.2.0
```

Kiểm tra rằng chỉ khi `major` và `minor` ngang nhau, `patch` mới quyết định. Sau đó thử các giá trị rất lớn nhưng vẫn nằm trong `int` để bảo đảm không có phép tính gộp hoặc phép trừ gây sai.

### Bài 3: đối chiếu bằng nhau và ngang hàng

Với hai `BigDecimal` từ chuỗi `"7.0"` và `"7.00"`:

1. Dự đoán `equals`.
2. Dự đoán dấu của `compareTo`.
3. Dự đoán kích thước khi đưa vào `HashSet`.
4. Dự đoán kích thước khi đưa vào `TreeSet`.
5. Giải thích kết quả bằng đúng hợp đồng của mỗi cấu trúc.

### Bài 4: thiết kế một kiểu giá trị mới

Thiết kế kiểu `Point` có hai tọa độ nguyên `x`, `y`, với thứ tự được chọn rõ là so `x` trước rồi `y`.

- Dùng một kiểu bất biến.
- Cài đặt `Comparable<Point>` bằng hàm so sánh an toàn.
- Bảo đảm hai điểm ngang hàng khi cả hai tọa độ bằng nhau.
- Kiểm tra sự nhất quán với `equals`.
- Sắp danh sách có điểm trùng và đối chiếu với số phần tử của `TreeSet`.
- Giải thích vì sao đây là thứ tự đã quy ước cho kiểu, không phải khoảng cách đến gốc tọa độ.

Tiêu chí hoàn thành là quy tắc, mã cài đặt và hành vi collection đều thống nhất, kể cả khi đổi chiều so sánh hoặc dùng dữ liệu ở biên.
