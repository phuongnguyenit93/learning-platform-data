# `Comparable<T>` và ý nghĩa của thứ tự tự nhiên

Trong Java, có những kiểu dữ liệu mà ta có thể sắp xếp theo một quy tắc mặc định có ý nghĩa: số nguyên từ nhỏ đến lớn, ngày tháng từ sớm đến muộn, phiên bản theo số `major` rồi đến `minor`. Quy tắc mặc định đó gọi là **thứ tự tự nhiên (natural ordering)**.

Giao diện `java.lang.Comparable<T>` cho phép **chính kiểu dữ liệu** công bố thứ tự tự nhiên của các giá trị thuộc kiểu đó. Phương thức cốt lõi là `compareTo(T other)`. Các thuật toán và cấu trúc như `Collections.sort`, `List.sort(null)`, `Arrays.sort`, `TreeSet` và `TreeMap` có thể sử dụng thứ tự này khi không được cung cấp một `Comparator` khác.

Vấn đề quan trọng khi học `Comparable` không chỉ là “viết hàm trả về -1, 0 hoặc 1”. Cần hiểu **giá trị âm/0/dương có nghĩa gì, hợp đồng so sánh yêu cầu điều gì, quan hệ với `equals` ra sao, và vì sao `TreeSet`/`TreeMap` có thể coi hai đối tượng là trùng khi `compareTo` trả về 0**.

## 1. `Comparable<T>` là gì?

Giao diện có dạng khái quát:

~~~java
public interface Comparable<T> {
    int compareTo(T other);
}
~~~

Kiểu `T` là kiểu giá trị mà đối tượng hiện tại có thể so sánh. Ví dụ một `Version` triển khai `Comparable<Version>` thì phương thức `compareTo` nhận một `Version`, cho phép trình biên dịch kiểm tra kiểu của đối số.

Kết quả của `a.compareTo(b)` được hiểu theo **dấu**, không nhất thiết theo giá trị tuyệt đối:

| Kết quả | Ý nghĩa |
| --- | --- |
| Số âm | `a` đứng **trước** `b` theo thứ tự tự nhiên. |
| `0` | `a` và `b` **tương đương trong quan hệ sắp xếp**. |
| Số dương | `a` đứng **sau** `b` theo thứ tự tự nhiên. |

Dấu âm có thể là `-1`, `-2` hoặc một số âm khác tùy cách cài đặt; tương tự dấu dương **không bắt buộc bằng `1`**. Khi xử lý kết quả, hãy kiểm tra `< 0`, `== 0` hoặc `> 0`, không kiểm tra cố định `== -1` hay `== 1`.

~~~java
int result = a.compareTo(b);
if (result < 0) {
    // a đứng trước b
} else if (result == 0) {
    // a và b tương đương theo thứ tự
} else {
    // a đứng sau b
}
~~~

Đây là đoạn mã minh họa **bên trong một phương thức**, với `a` và `b` có kiểu hỗ trợ `Comparable`.

### Thứ tự tự nhiên khác thứ tự mong muốn trong từng màn hình

Một kiểu có thể có một thứ tự tự nhiên phù hợp nhất, nhưng ứng dụng đôi khi cần sắp xếp theo một tiêu chí khác. Ví dụ `Version` tự nhiên tăng dần theo số phiên bản, còn màn hình phát hành mới nhất có thể cần hiển thị **giảm dần**. Trường hợp đó nên cung cấp `Comparator` khi sắp xếp, thay vì đổi `compareTo` mỗi khi một màn hình có nhu cầu mới.

## 2. Cài đặt thứ tự tự nhiên cho một kiểu dữ liệu

Giả sử một phiên bản có hai thành phần `major` và `minor`. Ta định nghĩa `1.9 < 1.10 < 2.0` bằng cách so **số nguyên** của `major` trước, nếu bằng nhau mới so `minor`. Không so chuỗi biểu diễn phiên bản, bởi thứ tự từ điển của `"1.10"` và `"1.9"` có thể khác thứ tự số phiên bản mong muốn.

Tệp **`ComparableVersionDemo.java`**, chạy độc lập trên Java 17+:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ComparableVersionDemo {

    record Version(int major, int minor) implements Comparable<Version> {
        Version {
            if (major < 0 || minor < 0) {
                throw new IllegalArgumentException("Version must be nonnegative");
            }
        }

        @Override
        public int compareTo(Version other) {
            int byMajor = Integer.compare(major, other.major);
            if (byMajor != 0) {
                return byMajor;
            }
            return Integer.compare(minor, other.minor);
        }
    }

    public static void main(String[] args) {
        Version first = new Version(1, 9);
        Version second = new Version(1, 10);
        Version sameValue = new Version(1, 9);

        System.out.println(Integer.signum(first.compareTo(second)));
        System.out.println(Integer.signum(second.compareTo(first)));
        System.out.println(first.compareTo(sameValue));
        System.out.println(first.equals(sameValue));
        System.out.println(first == sameValue);

        List<Version> versions = new ArrayList<>(List.of(
            new Version(2, 0),
            new Version(1, 10),
            new Version(1, 9),
            new Version(2, 0)
        ));

        Collections.sort(versions);
        System.out.println(versions);

        Set<Version> unique = new TreeSet<>(versions);
        System.out.println(unique);
        System.out.println(unique.size());
        System.out.println(unique.contains(new Version(1, 10)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ComparableVersionDemo.java
java ComparableVersionDemo
~~~

Kết quả chính xác:

~~~text
-1
1
0
true
false
[Version[major=1, minor=9], Version[major=1, minor=10], Version[major=2, minor=0], Version[major=2, minor=0]]
[Version[major=1, minor=9], Version[major=1, minor=10], Version[major=2, minor=0]]
3
true
~~~

Phân tích:

1. `first.compareTo(second)` âm: phiên bản `1.9` đứng trước `1.10`. `second.compareTo(first)` dương. `Integer.signum` ở đây chỉ để in `-1` hoặc `1` dễ nhìn.
2. `first.compareTo(sameValue) == 0` vì cả hai cùng `major = 1` và `minor = 9`.
3. `first.equals(sameValue)` là `true` vì **record** sinh `equals` theo hai thành phần. Nhưng `first == sameValue` là `false`: đây vẫn là hai đối tượng độc lập.
4. `Collections.sort` sử dụng thứ tự tự nhiên do `Version.compareTo` định nghĩa, nên các phiên bản xuất hiện theo thứ tự `1.9`, `1.10`, `2.0`, `2.0`.
5. `TreeSet` sắp tăng dần và giữ một phần tử đại diện cho mỗi giá trị khác biệt theo phép so sánh. Hai bản `2.0` có kết quả so sánh `0`, nên `unique.size()` bằng `3`.
6. `contains(new Version(1, 10))` trả `true` dù tham số là instance vừa tạo, vì nó tương đương theo quan hệ sắp xếp của tập.

Ví dụ dùng `record` và hai trường nguyên thủy để `equals`, `hashCode` và `compareTo` có cùng ý nghĩa giá trị. Đây là một lựa chọn thiết kế **nhất quán và dễ dùng với collection**.

## 3. Hợp đồng của `compareTo`

`Comparable` đặt ra những quy tắc để một phép so sánh có thể dùng đáng tin cậy trong sắp xếp và cấu trúc cây. Ký hiệu `sgn(n)` là dấu của số nguyên `n` (`-1`, `0`, hoặc `1`).

### 3.1. Đổi chiều so sánh phải đổi dấu

Với hai đối tượng phù hợp `x`, `y`:

~~~text
sgn(x.compareTo(y)) == -sgn(y.compareTo(x))
~~~

Nếu `x` đứng trước `y`, thì `y` phải đứng sau `x`. Nếu một chiều bằng `0`, chiều còn lại cũng phải bằng `0`. Không phải điều kiện “hai kết quả số nguyên phải cộng lại đúng bằng 0”; chỉ **dấu** mới quan trọng.

### 3.2. Tính bắc cầu

Nếu `x > y` và `y > z` theo `compareTo`, thì `x > z`. Tương tự quan hệ tăng dần. Ví dụ phiên bản `2.0 > 1.10` và `1.10 > 1.9`, nên `2.0 > 1.9`.

Vi phạm tính bắc cầu có thể làm thuật toán sắp xếp hoạt động sai hoặc ném lỗi liên quan đến hợp đồng so sánh trong một số trường hợp.

### 3.3. Các giá trị tương đương phải ứng xử giống nhau khi so với giá trị khác

Nếu `x.compareTo(y) == 0`, thì với mọi `z` cùng miền so sánh:

~~~text
sgn(x.compareTo(z)) == sgn(y.compareTo(z))
~~~

Nói cách khác, khi `x` và `y` được coi là tương đương về thứ tự, chúng không được có quan hệ trái ngược với một giá trị thứ ba. Đây là yêu cầu quan trọng để các phép sắp xếp và tìm kiếm theo thứ tự hoạt động có ý nghĩa.

### 3.4. Xử lý `null` và kiểu không tương thích

Các triển khai `compareTo` nên ném `NullPointerException` khi đối số là `null`; `null` không được xem là một giá trị `Version` đứng trước mọi phiên bản. Nếu đối tượng truyền vào không thể so với đối tượng nhận, việc so sánh không hợp lệ có thể gây `ClassCastException`. Khai báo `Comparable<Version>` đã giúp ngăn nhiều trường hợp sai kiểu ngay khi biên dịch, nhưng raw type hoặc một số đường gọi qua collection vẫn có thể gây lỗi lúc chạy.

Một `Comparator` được thiết kế riêng có thể quy định vị trí `null` bằng các tiện ích như `Comparator.nullsFirst` hoặc `nullsLast`; điều đó không làm thay đổi hợp đồng mặc định của `Version.compareTo`.

## 4. `compareTo() == 0` có phải `equals() == true`?

**Không phải lúc nào cũng vậy.** Hai phương thức xác định hai quan hệ khác nhau:

- `equals(Object)` định nghĩa **bằng nhau** của đối tượng theo hợp đồng `Object`; `HashSet` và `HashMap` dựa vào `equals`/`hashCode` để phân biệt phần tử/key.
- `compareTo(T)` định nghĩa **thứ tự tự nhiên**; `compareTo == 0` có nghĩa hai giá trị **tương đương theo thứ tự**, không tự động khẳng định `equals` trả `true`.
- Một kiểu có thứ tự tự nhiên **nhất quán với `equals`** khi và chỉ khi `x.compareTo(y) == 0` tương đương `x.equals(y) == true` đối với các giá trị tương ứng.

Java **rất khuyến nghị** thứ tự tự nhiên nhất quán với `equals`, nhưng không bắt buộc mọi kiểu phải có tính chất này. Khi không nhất quán, lập trình viên phải hiểu hệ quả, đặc biệt khi dùng trong các sorted collections.

### Ví dụ đặc biệt: `BigDecimal`

`BigDecimal` xét **giá trị số học** khi `compareTo`, nhưng `equals` còn xét cả `scale`. Vì vậy `1.0` và `1.00` có thể tương đương theo thứ tự nhưng không bằng nhau theo `equals`.

Tệp **`BigDecimalOrderingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalOrderingDemo {
    public static void main(String[] args) {
        BigDecimal first = new BigDecimal("1.0");
        BigDecimal second = new BigDecimal("1.00");

        System.out.println(first.equals(second));
        System.out.println(first.compareTo(second));
        System.out.println(first.hashCode() == second.hashCode());

        Set<BigDecimal> hashValues = new HashSet<>();
        hashValues.add(first);
        hashValues.add(second);
        System.out.println(hashValues.size());

        Set<BigDecimal> sortedValues = new TreeSet<>();
        sortedValues.add(first);
        sortedValues.add(second);
        System.out.println(sortedValues.size());
        System.out.println(sortedValues.contains(second));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BigDecimalOrderingDemo.java
java BigDecimalOrderingDemo
~~~

Kết quả chuẩn:

~~~text
false
0
false
2
1
true
~~~

`HashSet` giữ hai phần tử vì chúng không bằng nhau theo `equals`; `TreeSet` chỉ giữ một phần tử vì kết quả `compareTo` bằng `0`. Không phải lỗi của `TreeSet`: đây là hệ quả trực tiếp từ quy tắc phân biệt phần tử của một **sorted set**. Khi dùng `BigDecimal`, cần xác định rõ nghiệp vụ quan tâm cả `scale` hay chỉ quan tâm giá trị số học.

Trong bài toán tự thiết kế kiểu mới, thông thường nên làm cho `compareTo == 0` trùng với `equals == true` để hạn chế bất ngờ. Với `Version`, cả hai phương thức đều xét `major` và `minor`, nên không có sự bất nhất này.

## 5. Vì sao `TreeSet` và `TreeMap` dùng kết quả so sánh để nhận diện khóa?

`TreeSet` giữ các phần tử có thứ tự và `TreeMap` giữ các khóa có thứ tự. Nếu dùng thứ tự tự nhiên, chúng xác định tính tương đương của phần tử/key bằng `compareTo(...) == 0`; nếu được truyền một `Comparator`, chúng dùng kết quả `compare(...) == 0` của comparator đó.

| Cấu trúc | Cách phân biệt phần tử hoặc key |
| --- | --- |
| `HashSet` | Dùng `hashCode` để tổ chức tìm kiếm và `equals` để xác định trùng giá trị. |
| `HashMap` | Dùng `hashCode` và `equals` của key. |
| `TreeSet` | Dùng `compareTo == 0` hoặc `Comparator.compare == 0` để xác định tương đương theo thứ tự. |
| `TreeMap` | Dùng `compareTo == 0` hoặc `Comparator.compare == 0` đối với key. |

Ví dụ, với `TreeMap<Version, String>` dùng tự nhiên, gọi `put(new Version(1, 9), "old")` rồi `put(new Version(1, 9), "new")` sẽ giữ **một entry** cho `1.9`, với value `"new"`. Một instance key mới không nhất thiết tạo entry mới.

Tuy nhiên, nếu `compareTo` của một lớp **không nhất quán** với `equals`, sorted set/map có thể không tuân thủ đúng ngữ nghĩa tổng quát mà `Set`/`Map` đòi hỏi ở những tình huống có các đối tượng `equals` khác nhau. Vì vậy, đây là một rủi ro API thực tế, không chỉ là một chi tiết toán học của thứ tự.

## 6. Lỗi cài đặt: lấy hiệu hai số để so sánh

Một lỗi phổ biến là viết:

~~~java
@Override
public int compareTo(Version other) {
    return major - other.major; // Ví dụ sai: dễ overflow, bỏ qua minor.
}
~~~

Đoạn trên minh họa lỗi trong ngữ cảnh lớp `Version`, không phải mã thay thế cho phiên bản chính xác ở mục 2. Phép trừ `int` có thể **tràn số**; sau khi overflow, dấu của hiệu có thể bị đảo và làm vi phạm thứ tự mong muốn.

Ví dụ nhỏ chạy trong thân một phương thức:

~~~java
int a = Integer.MAX_VALUE;
int b = -1;

System.out.println(a - b);              // -2147483648 (overflow)
System.out.println(Integer.compare(a,b)); // 1
~~~

Ở đây `a` lớn hơn `b`, nhưng `a - b` trở thành số âm do tràn miền `int`, dễ làm thuật toán sắp xếp đưa giá trị lớn lên trước giá trị nhỏ. **Dùng `Integer.compare(a, b)`**, `Long.compare`, `Double.compare`, hoặc `compareTo` có sẵn cho kiểu thích hợp.

Tránh cả việc trả `1` cho mọi cặp khác nhau: nếu `x > y` luôn `true` và `y > x` cũng luôn `true`, hợp đồng đổi chiều so sánh đã bị phá vỡ.

## 7. Thứ tự tự nhiên và `Comparator<T>`

`Comparable<T>` định nghĩa thứ tự **ngay trong class**. Còn `java.util.Comparator<T>` là một đối tượng riêng định nghĩa một cách so sánh, nên có thể tạo nhiều thứ tự cho cùng kiểu mà không sửa class.

| Nhu cầu | Chọn |
| --- | --- |
| Một thứ tự mặc định ổn định, hợp lý cho kiểu | `implements Comparable<T>` với `compareTo`. |
| Sắp xếp khác thứ tự mặc định ở một màn hình/chức năng | Truyền `Comparator<T>` cho thuật toán sắp xếp. |
| Đảo chiều thứ tự tự nhiên | `Comparator.reverseOrder()` hoặc `Comparator.naturalOrder().reversed()`. |
| So sánh nhiều trường với quy tắc tùy biến | `Comparator.comparing(...).thenComparing(...)`. |

Ví dụ đầy đủ khác cho `Version`, vẫn dùng cùng lớp record từ tệp `ComparableVersionDemo.java` ở mục 2:

~~~java
List<Version> latestFirst = new ArrayList<>(List.of(
    new Version(1, 9), new Version(2, 0), new Version(1, 10)
));

latestFirst.sort(java.util.Comparator.reverseOrder());
System.out.println(latestFirst);
~~~

Khi chèn vào `main` của `ComparableVersionDemo`, đoạn trên sẽ in:

~~~text
[Version[major=2, minor=0], Version[major=1, minor=10], Version[major=1, minor=9]]
~~~

`Version.compareTo` **không bị sửa**. Chỉ thao tác sắp xếp này sử dụng thứ tự đảo chiều. Có thể dùng `List.sort(null)` để quay về thứ tự tự nhiên.

Một kiểu có thể triển khai `Comparable`, nhưng khi truyền một `Comparator` vào `TreeSet` hoặc `TreeMap`, **comparator được dùng** để xác định thứ tự và các phần tử/key tương đương. Do đó, comparator cũng cần tuân thủ hợp đồng so sánh và nên nhất quán với `equals` nếu collection cần thể hiện đúng ngữ nghĩa `Set`/`Map` tổng quát.

## 8. Một số kiểu Java đã có thứ tự tự nhiên

| Kiểu | Ý nghĩa thứ tự tự nhiên |
| --- | --- |
| `Integer`, `Long`, `BigInteger` | Thứ tự tăng dần theo giá trị số. |
| `String` | Thứ tự từ điển dựa trên giá trị các đơn vị mã UTF-16; phân biệt chữ hoa/chữ thường. |
| `LocalDate` | Ngày sớm hơn đứng trước ngày muộn hơn. |
| `Instant` | Thời điểm sớm hơn đứng trước thời điểm muộn hơn. |
| `BigDecimal` | Theo giá trị số học, có thể không nhất quán với `equals` do `scale`. |
| `Enum` | Thứ tự khai báo hằng enum trong kiểu enum đó. |

Không nên suy ra rằng thứ tự tự nhiên của `String` là thứ tự ngôn ngữ phù hợp với người đọc tiếng Việt hoặc mọi locale. Khi cần sắp xếp văn bản theo quy tắc ngôn ngữ, xem xét `Collator` hay quy tắc locale thích hợp qua một `Comparator`, thay vì giả định `String.compareTo` xử lý phân loại chữ theo ngôn ngữ tự nhiên.

Ngoài ra, **không phải mọi class Java đều triển khai `Comparable`**. Sắp xếp một danh sách các đối tượng không có thứ tự tự nhiên (và không cung cấp comparator) có thể gây `ClassCastException` khi thuật toán cần so sánh các phần tử. Muốn sắp xếp các đối tượng như vậy, định nghĩa `Comparator` hoặc triển khai `Comparable` nếu thứ tự mặc định thực sự hợp lý.

## 9. Lưu ý về tính ổn định và dữ liệu có thể thay đổi

Thứ tự tự nhiên thường dựa vào các trường xác định giá trị của đối tượng. Nếu những trường đó **có thể thay đổi** khi đối tượng đã nằm trong `TreeSet` hoặc đang làm key của `TreeMap`, cấu trúc cây có thể không còn được tổ chức phù hợp với thứ tự mới. Điều này dẫn tới việc `contains`, `get` hoặc `remove` không tìm thấy giá trị mong muốn.

Vì vậy, với kiểu dùng làm phần tử của sorted set hoặc key của sorted map, **ưu tiên bất biến** đối với các trường tham gia phép so sánh. `Version` ở mục 2 là record chứa hai `int` không thay đổi sau khi tạo, phù hợp với mục tiêu đó.

Cũng không nên cài đặt `compareTo` dựa trên một nguồn thay đổi theo thời gian như đồng hồ, random, hoặc trạng thái bên ngoài không ổn định. Với cùng hai đối tượng mà thứ tự thay đổi bất ngờ, phép sắp xếp và tra cứu có thể sai.

## 10. Quy trình thiết kế và kiểm tra `Comparable<T>`

1. **Xác định ý nghĩa thứ tự tự nhiên** của kiểu. Viết rõ trường chính và trường phụ dùng để phân xử khi trường chính bằng nhau.
2. **Triển khai `Comparable<T>`** và override `public int compareTo(T other)`. Dùng các phép so an toàn như `Integer.compare`, `Long.compare`, `String.compareTo` thay vì trừ trực tiếp các số nguyên.
3. **Kiểm tra dấu và hợp đồng:** đổi chiều phải đổi dấu; thứ tự phải bắc cầu; hai giá trị `compareTo == 0` phải so với giá trị thứ ba theo cùng chiều.
4. **Đối chiếu `equals` và `hashCode`:** cố gắng để `compareTo == 0` tương đương `equals == true` cho kiểu tự thiết kế, nhất là khi dùng `TreeSet`/`TreeMap`.
5. **Thử sắp xếp nhiều phần tử**, trong đó có dữ liệu trùng trường chính nhưng khác trường phụ; xác minh thứ tự sau `Collections.sort` hoặc `List.sort(null)`.
6. **Thử với sorted collection:** hai instance khác nhau nhưng `compareTo == 0` có được coi là một phần tử/key không? Đó có phù hợp nghiệp vụ không?
7. **Giữ trường so sánh ổn định** sau khi thêm vào cấu trúc cây; dùng `Comparator` riêng nếu chức năng khác cần một thứ tự khác.

### Tự kiểm tra

1. `a.compareTo(b)` trả `-5`. Điều gì được bảo đảm về thứ tự của `a` và `b`? Có phải mọi lần so sánh hợp lệ chỉ được trả `-1`, `0`, `1`?
2. `new Version(1, 9)` và `new Version(1, 10)` đối tượng nào đứng trước trong ví dụ? Vì sao không nên so chuỗi `"1.9"` với `"1.10"` để quyết định?
3. Hai đối tượng có `compareTo == 0` nhưng `equals == false`. Nếu đưa vào `TreeSet` và `HashSet`, điều gì có thể khác nhau?
4. Tại sao `return a - b;` trong `compareTo` có thể gây sai kết quả với giá trị `int` rất lớn và rất nhỏ?
5. Nếu một kiểu đã có thứ tự tự nhiên tăng dần nhưng một màn hình muốn giảm dần, nên sửa `compareTo` hay truyền `Comparator.reverseOrder()`?
6. Nếu thay đổi trường dùng trong `compareTo` của key đang nằm trong `TreeMap`, điều gì có thể xảy ra khi tìm kiếm key đó?

**Ghi nhớ:** `Comparable<T>` định nghĩa **thứ tự tự nhiên** qua `compareTo(T)`; **âm** nghĩa là đứng trước, **0** là tương đương theo thứ tự, **dương** là đứng sau. Quan hệ này phải nhất quán về dấu và tính bắc cầu. Nên giữ `compareTo == 0` nhất quán với `equals == true` để tránh bất ngờ trong `TreeSet`/`TreeMap`, và dùng `Comparator` cho những quy tắc sắp xếp riêng.