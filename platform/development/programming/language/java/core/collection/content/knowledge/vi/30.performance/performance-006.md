# Tránh duyệt LinkedList bằng get theo chỉ số

## 1. Một vòng lặp đúng kết quả vẫn có thể sai về hiệu năng

Đoạn mã sau rất quen thuộc khi làm việc với danh sách:

```java
long total = 0;
for (int i = 0; i < values.size(); i++) {
    total += values.get(i);
}
```

Đây là đoạn mã minh họa bên trong một phương thức; `values` được giả định là danh sách số nguyên không chứa `null`.

Nếu `values` là `ArrayList`, truy cập phần tử theo chỉ số có chi phí hằng số và một lượt duyệt như trên có chi phí tuyến tính theo số phần tử. Nếu `values` là `LinkedList`, mỗi lần `get(i)` phải tìm nút ở vị trí `i`. Lặp lại việc tìm vị trí cho mọi chỉ số làm tổng công việc tăng theo bậc hai.

Vấn đề khó nhận ra vì:

- Mã vẫn trả về kết quả chính xác.
- Chỉ có một vòng lặp hiện ra trong mã gọi.
- Dữ liệu nhỏ có thể chạy đủ nhanh để không lộ lỗi.
- Biến thường được khai báo bằng `List`, khiến người đọc quên xem đối tượng thực tế là loại danh sách nào.

Để duyệt tuần tự một `LinkedList`, hãy dùng vòng `for-each`, `Iterator` hoặc `ListIterator` phù hợp. Các cách này giữ vị trí hiện tại và đi tiếp theo liên kết, thay vì yêu cầu danh sách tìm lại vị trí từ đầu hoặc cuối sau mỗi bước.

## 2. Hiểu cơ chế: chỉ số không phải địa chỉ của nút

### 2.1. Mảng và danh sách liên kết trả lời hai câu hỏi khác nhau

Với cấu trúc dựa trên mảng, biết chỉ số cho phép xác định trực tiếp ô chứa phần tử. Với danh sách liên kết đôi, mỗi nút giữ phần tử cùng liên kết đến nút trước và nút sau:

```text
first                                              last
  |                                                  |
  v                                                  v
[10] <-> [20] <-> [30] <-> [40] <-> [50] <-> [60] <-> [70] <-> [80]
 0        1        2        3        4        5        6        7
```

Các số `0..7` ở dòng dưới là vị trí logic. Chúng không tạo ra một mảng tra cứu từ chỉ số đến nút.

`LinkedList` hỗ trợ API `get(index)` vì nó thực hiện giao diện `List`, nhưng để lấy phần tử ở một chỉ số bất kỳ, nó phải lần theo liên kết. Việc một phương thức tồn tại trong giao diện không đồng nghĩa mọi triển khai có cùng chi phí thực hiện phương thức đó.

Tài liệu Java mô tả rõ truy cập theo chỉ số trên `LinkedList` sẽ đi từ đầu hoặc cuối, chọn phía gần vị trí cần tìm hơn. [Tài liệu LinkedList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

### 2.2. Đi từ phía gần hơn vẫn không tạo ra truy cập hằng số

Giả sử danh sách có `n` phần tử và `0 <= i < n`. Số bước lần theo liên kết để tới nút `i`, theo cơ chế trên, là:

```text
h(i) = min(i, n - 1 - i)
```

Cần tính thêm một lượng công việc hằng số để kiểm tra chỉ số và lấy giá trị, nên chi phí một lần gọi có thể mô tả bằng:

```text
get(i): Θ(1 + min(i, n - 1 - i))
```

Ví dụ với `n = 8`:

| Chỉ số `i` | Phía bắt đầu | Số bước theo liên kết |
| --- | --- | --- |
| 0 | Đầu | 0 |
| 1 | Đầu | 1 |
| 2 | Đầu | 2 |
| 3 | Đầu | 3 |
| 4 | Cuối | 3 |
| 5 | Cuối | 2 |
| 6 | Cuối | 1 |
| 7 | Cuối | 0 |

`get(0)` và `get(n - 1)` có chi phí hằng số. Những vị trí gần giữa cần số bước tỷ lệ với `n`. Vì thế nói “mọi `get(i)` đều phải đi qua `n` nút” là không chính xác; nói “truy cập chỉ số bất kỳ trên LinkedList có trường hợp xấu tuyến tính” mới đúng.

Quan trọng hơn, `get(4)` không tận dụng nút mà lần `get(3)` trước đó vừa tìm ra. Mỗi lời gọi định vị lại nút từ một đầu danh sách. Đây là điểm khác biệt với iterator. Có thể kiểm chứng cơ chế định vị trong mã nguồn OpenJDK 17, tại phương thức nội bộ `node(index)`. [Mã nguồn LinkedList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java)

## 3. Vì sao một vòng for lại có tổng chi phí bậc hai?

### 3.1. Cộng công việc ẩn trong từng get

Xét vòng lặp gọi `get(0)`, `get(1)`, ..., `get(n - 1)` đúng một lần trên danh sách không bị thay đổi trong lúc duyệt.

Tổng số bước theo liên kết là:

```text
H(n) = tổng min(i, n - 1 - i), với i từ 0 đến n - 1
```

Với `n = 8`, tổng là:

```text
0 + 1 + 2 + 3 + 3 + 2 + 1 + 0 = 12
```

Với số phần tử lớn hơn:

- Nếu `n = 2k`, tổng là `k(k - 1)`.
- Nếu `n = 2k + 1`, tổng là `k²`.

Hai trường hợp có thể viết gọn:

```text
H(n) = floor((n - 1)² / 4), với n >= 1
```

Ngoài các bước theo liên kết, vẫn có `n` lần lấy phần tử và xử lý điều kiện vòng lặp. Tổng chi phí duyệt là:

```text
T(n) = Θ(n + H(n)) = Θ(n²)
```

Đây là kết luận cho vòng lặp duyệt toàn bộ bằng chỉ số, không phải kết luận rằng mọi cách dùng `LinkedList` đều bậc hai.

### 3.2. Đọc bảng tăng trưởng

| Số phần tử `n` | Số lần gọi `get(i)` | Tổng bước theo liên kết `H(n)` |
| --- | --- | --- |
| 8 | 8 | 12 |
| 1.000 | 1.000 | 249.500 |
| 2.000 | 2.000 | 999.000 |
| 4.000 | 4.000 | 3.998.000 |
| 10.000 | 10.000 | 24.995.000 |

Tăng kích thước gấp đôi làm số bước theo liên kết tiến gần mức gấp bốn. Việc đi từ đầu gần hơn giảm công việc so với luôn đi từ đầu, nhưng không đổi bậc tăng.

Bảng đếm bước theo mô hình định vị nút, không phải số nano giây, số lệnh máy hay số lần truy cập bộ nhớ thực tế. Nó giải thích nguyên nhân thuật toán; không dự đoán thời gian cụ thể trên mọi máy.

### 3.3. Đưa size ra ngoài vòng lặp không giải quyết gốc vấn đề

Đổi thành:

```java
int n = values.size();
for (int i = 0; i < n; i++) {
    process(values.get(i));
}
```

không làm việc duyệt `LinkedList` trở thành tuyến tính. Trong triển khai này, kích thước đã được lưu lại; chi phí chi phối là tìm nút trong `get(i)`, không phải đếm lại toàn bộ danh sách trong `size()`.

Đoạn trên là mã minh họa; `process` đại diện cho công việc xử lý một phần tử. Nếu mỗi lần xử lý có chi phí riêng lớn, tổng chi phí cần tính cả phần đó. Tuy nhiên, công việc tìm lại nút vẫn tồn tại và có thể tránh được.

## 4. Duyệt tuần tự bằng iterator

### 4.1. Chỉ cần đọc từng phần tử: dùng for-each

```java
long total = 0;
for (int value : values) {
    total += value;
}
```

Với đối tượng triển khai `Iterable` như `LinkedList`, vòng `for-each` duyệt thông qua iterator. Nó không được biến thành chuỗi `get(0)`, `get(1)`, ... như vòng lặp chỉ số ở đầu bài.

Iterator của danh sách liên kết giữ nút kế tiếp cần đọc. Mỗi lần `next()` lấy giá trị rồi chuyển sang nút liền sau. Một lượt duyệt `n` phần tử có chi phí `Θ(n)`, nếu công việc xử lý mỗi phần tử là hằng số.

Đây thường là cách rõ nhất khi thuật toán chỉ cần giá trị, không cần chỉnh sửa cấu trúc danh sách trong lúc duyệt.

### 4.2. Cần điều khiển việc duyệt: dùng Iterator tường minh

```java
long total = 0;
Iterator<Integer> iterator = values.iterator();
while (iterator.hasNext()) {
    total += iterator.next();
}
```

Đoạn mã minh họa này cần import `java.util.Iterator` và `values` không chứa `null` khi thực hiện phép cộng bằng cách mở hộp `Integer` sang `int`.

Khác biệt về cơ chế:

```text
Duyệt bằng get(i):
    yêu cầu vị trí 0 -> tìm nút
    yêu cầu vị trí 1 -> tìm lại nút
    yêu cầu vị trí 2 -> tìm lại nút
    ...

Duyệt bằng một iterator:
    bắt đầu tại đầu danh sách
    đọc nút hiện tại -> đi tới nút kế
    đọc nút hiện tại -> đi tới nút kế
    ...
```

Việc giữ lại vị trí mới là điều tiết kiệm công việc. Chỉ đổi cú pháp mà vẫn gọi `get(i)` trong phần thân thì không đạt mục tiêu đó.

### 4.3. Cần số thứ tự: tăng một biến đếm bên cạnh iterator

Không nhất thiết phải dùng truy cập chỉ số chỉ vì đầu ra cần số thứ tự.

Ví dụ minh họa bên trong một phương thức, không sửa cấu trúc danh sách trong vòng lặp:

```java
int index = 0;
for (String value : names) {
    System.out.println(index + ": " + value);
    index++;
}
```

Biến `index` theo dõi thứ tự đang duyệt; nó không được dùng để tìm lại phần tử. Do đó vẫn có một lượt duyệt tuyến tính trên `LinkedList`.

Nếu thuật toán cần vị trí con trỏ hoặc duyệt hai chiều, `ListIterator` cung cấp trực tiếp những thao tác đó.

## 5. Duyệt ngược và cập nhật bằng ListIterator

### 5.1. Duyệt ngược cũng không nên gọi get giảm dần

Vòng lặp này vẫn có tổng chi phí bậc hai trên `LinkedList`:

```java
for (int i = values.size() - 1; i >= 0; i--) {
    process(values.get(i));
}
```

Nó chỉ đổi thứ tự của cùng các lần định vị nút. Dùng một `ListIterator` bắt đầu ở cuối sẽ giữ vị trí khi đi ngược:

```java
ListIterator<Integer> iterator = values.listIterator(values.size());
while (iterator.hasPrevious()) {
    int value = iterator.previous();
    process(value);
}
```

Hoặc, khi biến có kiểu `LinkedList`/`Deque` phù hợp, có thể dùng `descendingIterator()` để duyệt ngược. Hãy chọn API phù hợp với kiểu được công bố cho phương thức, thay vì ép kiểu chỉ để dùng một cách viết ngắn hơn.

### 5.2. Tạo iterator một lần rồi đi tiếp

`ListIterator` có con trỏ nằm giữa các phần tử, cho phép `next()`, `previous()` và lấy chỉ số liên quan tới vị trí con trỏ. `set()` tác động lên phần tử vừa được trả về bởi `next()` hoặc `previous()`, theo điều kiện của API. [Tài liệu ListIterator của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html)

Ví dụ cập nhật mọi giá trị trong một danh sách có thể sửa đổi:

```java
ListIterator<Integer> iterator = values.listIterator();
while (iterator.hasNext()) {
    int current = iterator.next();
    iterator.set(current * 10);
}
```

Duyệt một lần và cập nhật ngay tại vị trí đã tìm được tránh dạng sau:

```java
for (int i = 0; i < values.size(); i++) {
    values.set(i, values.get(i) * 10);
}
```

Trong dạng chỉ số, cả `get(i)` lẫn `set(i, ...)` đều cần định vị nút. Hai lần tìm ở mỗi chỉ số vẫn tạo tổng bậc hai.

Cũng không nên tạo lại `values.listIterator(i)` ở mỗi bước. Khởi tạo iterator tại một vị trí ở giữa có thể phải tìm vị trí đó. Hiệu quả tuyến tính đến từ việc **dùng lại cùng một iterator để di chuyển tuần tự**, không đến từ tên kiểu `ListIterator` đứng riêng.

## 6. Chương trình Java 17+ chạy đầy đủ

Chương trình sau có ba mục đích:

1. Chứng minh các cách duyệt trả về cùng tổng.
2. Đưa ra số bước định vị theo mô hình, không dựa vào phép đo thời gian nhiễu.
3. Minh họa duyệt ngược và chỉnh sửa an toàn thông qua iterator của chính vòng lặp.

Lưu thành `LinkedListTraversalDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListTraversalDemo {
    private static long sumByIndex(List<Integer> values) {
        long total = 0;
        for (int i = 0; i < values.size(); i++) {
            total += values.get(i);
        }
        return total;
    }

    private static long sumByForEach(List<Integer> values) {
        long total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    private static long sumByIterator(List<Integer> values) {
        long total = 0;
        Iterator<Integer> iterator = values.iterator();
        while (iterator.hasNext()) {
            total += iterator.next();
        }
        return total;
    }

    private static List<Integer> reverseValues(List<Integer> values) {
        List<Integer> result = new ArrayList<>();
        ListIterator<Integer> iterator = values.listIterator(values.size());
        while (iterator.hasPrevious()) {
            result.add(iterator.previous());
        }
        return result;
    }

    private static long modeledIndexHops(int size) {
        long hops = 0;
        for (int i = 0; i < size; i++) {
            hops += Math.min(i, size - 1 - i);
        }
        return hops;
    }

    public static void main(String[] args) {
        List<Integer> values = new LinkedList<>(
                List.of(10, 20, 30, 40, 50, 60, 70, 80));
        System.out.println("input = " + values);
        System.out.println("sum by index = " + sumByIndex(values));
        System.out.println("sum by for-each = " + sumByForEach(values));
        System.out.println("sum by iterator = " + sumByIterator(values));
        System.out.println("reverse = " + reverseValues(values));

        for (int size : new int[] {8, 1000, 2000, 4000}) {
            System.out.println("n=" + size
                    + ", modeled index hops=" + modeledIndexHops(size));
        }

        List<Integer> odds = new LinkedList<>(List.of(1, 2, 3, 4, 5, 6));
        Iterator<Integer> removalIterator = odds.iterator();
        while (removalIterator.hasNext()) {
            int value = removalIterator.next();
            if (value % 2 == 0) {
                removalIterator.remove();
            }
        }
        System.out.println("after removing even values = " + odds);

        ListIterator<Integer> updateIterator = odds.listIterator();
        while (updateIterator.hasNext()) {
            int value = updateIterator.next();
            updateIterator.set(value * 10);
        }
        System.out.println("after multiplying by ten = " + odds);
        System.out.println("input remains = " + values);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LinkedListTraversalDemo.java
java LinkedListTraversalDemo
```

Stdout:

```text
input = [10, 20, 30, 40, 50, 60, 70, 80]
sum by index = 360
sum by for-each = 360
sum by iterator = 360
reverse = [80, 70, 60, 50, 40, 30, 20, 10]
n=8, modeled index hops=12
n=1000, modeled index hops=249500
n=2000, modeled index hops=999000
n=4000, modeled index hops=3998000
after removing even values = [1, 3, 5]
after multiplying by ten = [10, 30, 50]
input remains = [10, 20, 30, 40, 50, 60, 70, 80]
```

`modeledIndexHops()` cộng khoảng cách theo mô hình đã phân tích; nó không gắn bộ đếm vào các nút nội bộ của Java và không đo thời gian. Hàm tính mô hình tự nó chạy tuyến tính theo tham số `size`, dù con số mà nó tính biểu diễn tổng công việc bậc hai của một cách duyệt khác.

Ba hàm tính tổng không có khác biệt về kết quả trên dữ liệu này. Sự khác biệt nằm ở lượng công việc tìm phần tử. Một kiểm thử chỉ so sánh tổng bằng `360` sẽ không phát hiện vấn đề hiệu năng của `sumByIndex()`.

## 7. Các cách đổi cú pháp nhưng vẫn giữ nguyên lỗi

### 7.1. Duyệt dãy chỉ số bằng Stream

Đoạn minh họa này vẫn gọi `get(i)` cho từng chỉ số:

```java
long total = IntStream.range(0, values.size())
        .mapToLong(i -> values.get(i))
        .sum();
```

Nó cần import `java.util.stream.IntStream`. Với `values` là `LinkedList`, thay `for` bằng một luồng chỉ số không thay đổi chi phí định vị nút. Tổng công việc vẫn bậc hai.

Nếu chỉ cần duyệt các giá trị, có thể dùng vòng `for-each` hoặc luồng phần tử:

```java
long total = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
```

Luồng phần tử tuần tự của `LinkedList` duyệt cấu trúc qua cơ chế của collection thay vì tự tạo chuỗi truy cập chỉ số như ví dụ đầu. Không cần dùng Stream chỉ để đạt độ phức tạp tuyến tính; vòng `for-each` đã làm được điều đó.

Cả hai ví dụ tính tổng đều giả định không có `null`. Cho phép lưu `null` trong `LinkedList` không làm phép mở hộp số nguyên chấp nhận `null`.

### 7.2. Giữ một biến chỉ số trong for-each rồi gọi get lại

```java
int index = 0;
for (Integer ignored : values) {
    process(values.get(index++));
}
```

Đoạn trên đã có iterator để đọc phần tử, nhưng bỏ giá trị nhận được rồi tìm lại bằng chỉ số. Hãy xử lý trực tiếp biến phần tử của vòng lặp.

### 7.3. Dùng indexOf cho từng giá trị để lấy số thứ tự

Nếu trong mỗi lượt duyệt ta lại gọi `values.indexOf(value)`, đó là một cuộc tìm kiếm mới. Tổng công việc có thể trở thành bậc hai; với phần tử trùng nhau, chỉ số nhận được còn là vị trí xuất hiện đầu tiên chứ không nhất thiết là vị trí đang duyệt.

Dùng biến đếm hoặc `ListIterator.nextIndex()` phù hợp với mục tiêu thay vì tìm lại vị trí từ giá trị.

## 8. Thay đổi danh sách trong lúc duyệt: giữ đúng iterator và ngữ nghĩa

### 8.1. Đọc bằng for-each không cấp quyền xóa trực tiếp trên danh sách

Đoạn sau là ví dụ lỗi, không phải cách xóa nên dùng:

```java
for (Integer value : values) {
    if (value < 0) {
        values.remove(value);
    }
}
```

Xóa trực tiếp qua `values` thay đổi cấu trúc mà iterator của vòng `for-each` không quản lý. Với iterator thông thường của `LinkedList`, điều này có thể dẫn đến `ConcurrentModificationException`. Cơ chế phát hiện lỗi là nỗ lực tốt nhất; không dùng việc “chưa thấy exception” để kết luận cách duyệt đó an toàn. [Tài liệu LinkedList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

Khi cần lọc tại chỗ bằng vòng lặp, gọi `remove()` trên chính iterator sau khi `next()` trả về phần tử. Chương trình đầy đủ ở trên minh họa cách này. Không gọi `remove()` hai lần cho cùng một lần `next()`.

Việc tháo một nút đã được iterator tìm tới không cần tìm lại chỉ số. Tuy vậy, đừng suy rộng điều này thành “mọi thao tác xóa trên LinkedList đều hằng số”: xóa theo chỉ số hoặc tìm giá trị để xóa vẫn có thể phải duyệt để xác định nút.

### 8.2. Duyệt ngược không đồng nghĩa xóa các phần tử

`ListIterator` đi ngược hoặc `descendingIterator()` có thể đọc từ cuối về đầu mà giữ nguyên collection. Nếu dùng `removeFirst()`, `pollFirst()` hoặc thao tác lấy-xóa tương tự, cấu trúc nguồn bị tiêu thụ.

Tiêu thụ từng phần tử đầu có thể phù hợp với bài toán hàng đợi, nhưng không phải phép thay thế tương đương cho một lượt đọc giữ nguyên danh sách. Khi sửa mã để tối ưu, phải bảo toàn cả kết quả lẫn tác dụng lên dữ liệu nguồn.

### 8.3. Dùng iterator không làm collection tự an toàn giữa các luồng

Lợi ích ở đây là giữ vị trí khi duyệt trong điều kiện truy cập hợp lệ. Nó không cung cấp cơ chế đồng bộ cho một danh sách đang bị luồng khác thay đổi. Cần giải quyết quyền truy cập dữ liệu đồng thời riêng, thay vì coi iterator như một khóa bảo vệ.

## 9. Khi nào dùng ArrayList hoặc tạo bản sao?

### 9.1. Phân biệt nhu cầu duyệt tuần tự và truy cập vị trí

Nếu thuật toán chỉ cần một lượt đọc, sửa vòng lặp sang `for-each` hoặc iterator là đủ; không nhất thiết phải thay cấu trúc dữ liệu.

Nếu thuật toán thường xuyên truy cập các vị trí bất kỳ, chẳng hạn nhiều lần `get(randomIndex)`, có thể lựa chọn cấu trúc hỗ trợ truy cập chỉ số nhanh. Điều này là quyết định về mẫu thao tác, không phải khẩu hiệu rằng `LinkedList` luôn tốt hay luôn xấu.

Kiểu `List` không hứa chi phí truy cập hằng số cho mọi triển khai. Giao diện đánh dấu `RandomAccess` giúp thuật toán tổng quát nhận biết những danh sách hỗ trợ truy cập ngẫu nhiên nhanh và chọn chiến lược phù hợp. `ArrayList` thực hiện giao diện này, còn `LinkedList` không thực hiện. [Tài liệu RandomAccess của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html)

Với một phép duyệt đơn giản, không cần thêm nhánh `instanceof RandomAccess`: iterator đã biểu đạt đúng ý định duyệt tuần tự.

### 9.2. Một bản sao có chi phí và ngữ nghĩa riêng

Khi có nhiều truy cập chỉ số tiếp theo, có thể tạo bản sao:

```java
List<String> indexed = new ArrayList<>(linkedNames);
```

Đoạn minh họa này cần import `java.util.ArrayList` và `java.util.List`; `linkedNames` là danh sách nguồn.

Với nguồn `LinkedList`, sao chép các tham chiếu cần công việc tuyến tính và thêm bộ nhớ tuyến tính. Sau đó, truy cập chỉ số trên bản sao hỗ trợ mẫu xử lý dựa trên mảng.

Cần kiểm tra:

- Có đủ nhiều truy cập tiếp theo để đáng trả chi phí sao chép không?
- Chương trình có cần thấy những thay đổi cấu trúc sau này của danh sách nguồn không?
- Có được phép giữ thêm bộ nhớ `O(n)` không?

Đây là bản sao cấu trúc chứa các tham chiếu. Các đối tượng phần tử không được sao chép sâu. Thêm/xóa phần tử trong danh sách nguồn không tự cập nhật danh sách đích, nhưng nếu cùng tham chiếu tới một đối tượng có thể thay đổi, thay đổi bên trong đối tượng đó vẫn có thể được quan sát từ cả hai.

Nếu chỉ đọc một lần, sao chép rồi duyệt thường thêm công việc không cần thiết so với duyệt trực tiếp bằng iterator.

## 10. Kiểm tra một thay đổi tối ưu như thế nào?

### 10.1. Kiểm tra tính đúng trước

Khi đổi vòng lặp, hãy xác nhận:

- Phần tử vẫn được xử lý theo cùng thứ tự.
- Mỗi phần tử cần thiết được xử lý đúng số lần.
- Danh sách nguồn vẫn được giữ lại hoặc bị sửa đúng theo yêu cầu cũ.
- Dữ liệu rỗng, một phần tử, phần tử trùng và `null` được xử lý theo cùng hợp đồng.
- Mọi thao tác thêm/xóa trong lúc duyệt tuân theo API của iterator đang dùng.

Đối với ví dụ tính tổng, `null` phải được loại trừ hoặc có chính sách xử lý rõ ràng; thay kiểu vòng lặp không tự giải quyết vấn đề đó.

### 10.2. Kiểm tra cơ chế và tăng trưởng

Tìm những cuộc định vị bị lặp lại: `get(i)`, `set(i, ...)`, `listIterator(i)`, `indexOf(...)` bên trong vòng duyệt. Phải xét cả phương thức được gọi trong thân vòng lặp, không chỉ nhìn số vòng lặp ở mã ngoài.

Đo với nhiều kích thước dữ liệu nếu cần xác nhận tác động trong chương trình thực tế. Tránh xem một lần đo đồng hồ trên danh sách nhỏ là bằng chứng độ phức tạp. JVM còn có khởi động, JIT, cấp phát bộ nhớ, GC và nhiễu hệ thống.

Với phần thân chỉ làm công việc hằng số:

- Duyệt chỉ số toàn bộ `LinkedList`: tăng kích thước gấp đôi dẫn đến lượng công việc định vị gần gấp bốn khi `n` lớn.
- Một lượt iterator: lượng công việc tăng tuyến tính với số phần tử.

Các tỷ lệ này là dự đoán về bậc tăng, không phải cam kết thời gian chạy chính xác gấp bốn hoặc gấp hai trên mọi lần đo.

## 11. Bảng lựa chọn theo nhu cầu

| Nhu cầu | Cách làm phù hợp trên LinkedList | Điều cần tránh |
| --- | --- | --- |
| Đọc mọi giá trị theo thứ tự | `for-each` | `get(i)` cho mọi chỉ số |
| Đọc kèm số thứ tự | `for-each` + biến đếm, hoặc `ListIterator` | `indexOf(value)` lặp lại |
| Duyệt ngược giữ nguyên danh sách | Một `ListIterator` ở cuối hoặc `descendingIterator()` | Vòng `get(i)` giảm dần |
| Xóa một số phần tử trong lúc duyệt | `remove()` của chính iterator | Xóa trực tiếp trên danh sách trong `for-each` |
| Thay giá trị tại phần tử đang duyệt | `ListIterator.set()` sau khi đọc phần tử | `get(i)` rồi `set(i, ...)` trên mọi chỉ số |
| Xử lý một đoạn liên tiếp từ vị trí `k` | Định vị iterator một lần rồi đi tiếp | Tạo lại iterator tại từng chỉ số |
| Truy cập nhiều vị trí bất kỳ | Cân nhắc cấu trúc hỗ trợ truy cập chỉ số hoặc một bản sao phù hợp | Giả định mọi `List.get()` đều hằng số |

## 12. Tự kiểm tra và thực hành

### Câu 1: Duyệt chỉ số vẫn bậc hai nếu LinkedList biết chọn đầu gần hơn không?

Có. Tổng khoảng cách là `floor((n - 1)² / 4)` với `n >= 1`, nên vẫn tăng theo `Θ(n²)`. Chọn đầu gần hơn cải thiện hệ số, không thay đổi bậc tăng.

### Câu 2: Đã lưu values.size() vào một biến, vì sao vẫn chậm?

Vì mỗi `get(i)` vẫn phải định vị nút. Cắt bớt các lần gọi `size()` không loại bỏ tổng công việc tìm nút.

### Câu 3: Cần in số thứ tự, có bắt buộc dùng get(i) không?

Không. Dùng một biến đếm cùng `for-each`, hoặc lấy chỉ số con trỏ bằng `ListIterator` khi phù hợp. Số thứ tự của vòng duyệt không đòi hỏi truy cập phần tử bằng chỉ số.

### Câu 4: Chuyển sang IntStream.range(...).mapToObj(values::get) có giải quyết được không?

Không. Các cuộc gọi `get(i)` vẫn diễn ra. Hãy duyệt các giá trị trực tiếp thay vì tạo lại cách truy cập chỉ số bằng cú pháp khác.

### Bài thực hành

1. Thêm phương thức tính tổng số lẻ vào chương trình đầy đủ, dùng một lượt `for-each` và giữ nguyên nguồn.
2. Viết hàm tìm vị trí đầu tiên có giá trị lớn hơn một ngưỡng, dùng iterator kèm biến đếm và dừng ngay khi tìm được.
3. Giải thích chi phí khi tạo `listIterator(k)` một lần rồi đọc `r` phần tử liên tiếp, với các vị trí hợp lệ và không có sửa đổi ngoài iterator.
4. Xem lại một phương thức nhận `List<T>` trong mã của bạn: nó có vô tình giả định truy cập chỉ số nhanh không?

Gợi ý đối chiếu cho câu 3: chi phí gồm một lần định vị ban đầu cộng công việc đi tiếp qua `r` phần tử. Trên `LinkedList`, cận tổng là `O(n + r)`; nếu xét khoảng cách đến vị trí khởi đầu thì có thể mô tả chặt hơn theo khoảng cách đó. Không có `r` lần định vị độc lập như khi lặp lại `get(k + j)`.

Khi mục tiêu là đi qua các phần tử liên tiếp, hãy giữ vị trí và đi tiếp. Đó là lý do một iterator phù hợp với `LinkedList` hơn một chuỗi yêu cầu tìm lại các chỉ số.
