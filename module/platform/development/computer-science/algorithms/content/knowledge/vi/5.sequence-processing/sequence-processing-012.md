# Trộn các dãy đã có thứ tự

> **Chủ đề:** Computer Science Algorithms → Xử lý dãy.  
> **Mục tiêu:** Hiểu cách trộn hai hay nhiều dãy **đã được sắp xếp**, chứng minh kết quả đúng bằng bất biến, giữ đúng các phần tử trùng và thứ tự ổn định khi cần, chọn cách dùng bộ nhớ phù hợp, và tự cài đặt bằng Java 17+.

## 1. Bài toán và điều kiện đầu vào

Cho hai dãy:

- `A` gồm `m` phần tử, đã sắp xếp **không giảm**;
- `B` gồm `n` phần tử, cũng đã sắp xếp **không giảm** theo **cùng tiêu chí**.

Nhiệm vụ là tạo dãy `C` có `m+n` phần tử sao cho:

1. `C` được sắp xếp không giảm;
2. **mỗi phần tử của A và B xuất hiện trong C đúng số lần ban đầu** (*bảo toàn đa tập*, multiset);
3. nếu yêu cầu **trộn ổn định** (*stable merge*), các phần tử có khóa bằng nhau giữ thứ tự gốc theo quy ước đã xác định.

Ví dụ:

```text
A = [-4, 1, 1, 7]
B = [-3, 1, 6, 9]

C = [-4, -3, 1, 1, 1, 6, 7, 9]
```

Đây là phép **merge** trên các dãy đã có thứ tự. Nó khác với việc nối hai dãy rồi sắp xếp lại: nhờ khai thác thứ tự đã có, ta đạt thời gian **O(m+n)** thay vì thường cần **O((m+n) log(m+n))** cho sắp xếp so sánh tổng quát.

**Tiền điều kiện thiết yếu:** mỗi dãy đầu vào phải được sắp xếp theo cùng quan hệ thứ tự. Nếu một dãy tăng và một dãy giảm, hoặc hai dãy sắp xếp theo hai comparator khác nhau, quy tắc trộn trực tiếp sẽ không bảo đảm đúng.

### 1.1. Hai ý nghĩa của “ổn định”

Với mỗi dãy nguồn, khi trộn bằng hai con trỏ tăng dần, thứ tự tương đối của các phần tử trong **cùng dãy** luôn được giữ. Nếu hình dung dữ liệu gốc là phép nối `A` rồi `B`, để giữ ổn định cả **giữa hai dãy** khi các khóa bằng nhau, ta ưu tiên phần tử từ `A` khi hòa:

```text
Nếu A[i] <= B[j] thì lấy A[i]; ngược lại lấy B[j].
```

Ví dụ các bản ghi có khóa `time`:

```text
A = [(2,A1), (2,A2), (5,A3)]
B = [(2,B1), (4,B2)]

Trộn ổn định theo time:
[(2,A1), (2,A2), (2,B1), (4,B2), (5,A3)]
```

Dùng điều kiện `A[i] < B[j]` sẽ ưu tiên B khi hòa. Kết quả vẫn **được sắp xếp** và **đủ phần tử**, nhưng không ổn định so với quy ước nguồn nối `A` trước `B`. Nếu bài toán có tiêu chí phụ riêng, ví dụ ưu tiên timestamp rồi ID, phải mô tả rõ comparator và quy tắc hòa.

## 2. Trộn hai dãy bằng hai con trỏ

Đặt:

- `i`: vị trí phần tử chưa lấy đầu tiên trong `A`;
- `j`: vị trí phần tử chưa lấy đầu tiên trong `B`;
- `k`: vị trí tiếp theo để ghi vào `C`.

Vì cả hai dãy đã có thứ tự, phần tử nhỏ nhất còn lại trong `A` là `A[i]`, và phần tử nhỏ nhất còn lại trong `B` là `B[j]`. Phần tử nhỏ nhất của **hợp hai phần chưa lấy** phải là một trong hai đầu này. Do đó chỉ cần so sánh hai giá trị, lấy giá trị nhỏ hơn rồi dịch đúng con trỏ tương ứng.

**Pseudocode:**

```text
i = j = k = 0
while i < m AND j < n:
    if A[i] <= B[j]:       // Ưu tiên A khi hòa để trộn ổn định
        C[k] = A[i]
        i++
    else:
        C[k] = B[j]
        j++
    k++

while i < m:               // B đã hết
    C[k++] = A[i++]

while j < n:               // A đã hết
    C[k++] = B[j++]

return C
```

Ví dụ diễn tiến:

| Bước | Đầu A còn lại | Đầu B còn lại | Phần tử chọn | Prefix kết quả |
|---|---:|---:|---|---|
| 1 | -4 | -3 | -4 từ A | `[-4]` |
| 2 | 1 | -3 | -3 từ B | `[-4,-3]` |
| 3 | 1 | 1 | 1 từ A | `[-4,-3,1]` |
| 4 | 1 | 1 | 1 từ A | `[-4,-3,1,1]` |
| 5 | 7 | 1 | 1 từ B | `[-4,-3,1,1,1]` |
| 6 | 7 | 6 | 6 từ B | `[-4,-3,1,1,1,6]` |
| 7 | 7 | 9 | 7 từ A | `[-4,-3,1,1,1,6,7]` |
| 8 | A hết | 9 | Chép phần còn lại | `[-4,-3,1,1,1,6,7,9]` |

Điểm then chốt: **không cần tìm min của toàn bộ hai dãy** ở mỗi bước; hai đầu hiện tại đã đủ vì mọi phần tử phía sau không nhỏ hơn đầu tương ứng.

### 2.1. Ví dụ Java 17: hai mảng số nguyên

Lưu thành **MergeTwoSortedArrays.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class MergeTwoSortedArrays {
    // Tiền điều kiện: a, b đã sắp xếp không giảm.
    static int[] merge(int[] a, int[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        if (a.length > Integer.MAX_VALUE - b.length) {
            throw new IllegalArgumentException("Output array too large");
        }

        int[] result = new int[a.length + b.length];
        int i = 0;
        int j = 0;
        int k = 0;

        while (i < a.length && j < b.length) {
            if (a[i] <= b[j]) {
                result[k++] = a[i++];
            } else {
                result[k++] = b[j++];
            }
        }
        while (i < a.length) {
            result[k++] = a[i++];
        }
        while (j < b.length) {
            result[k++] = b[j++];
        }
        return result;
    }

    public static void main(String[] args) {
        int[] a = {-4, 1, 1, 7};
        int[] b = {-3, 1, 6, 9};

        System.out.println(Arrays.toString(merge(a, b)));
        System.out.println(Arrays.toString(merge(new int[0],
                                                 new int[]{2, 2})));
        System.out.println(Arrays.toString(merge(new int[0],
                                                 new int[0])));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MergeTwoSortedArrays.java
java MergeTwoSortedArrays
```

Stdout:

```text
[-4, -3, 1, 1, 1, 6, 7, 9]
[2, 2]
[]
```

Hàm **không thay đổi** `a`, `b`. Mảng kết quả được cấp phát đúng `m+n` phần tử. Trường hợp cả hai rỗng, một dãy rỗng, phần tử âm và các phần tử trùng đều được xử lý. Phép kiểm tra tổng độ dài nhằm tránh cộng hai số `int` bị tràn, nhưng trong thực tế còn có thể gặp giới hạn bộ nhớ/độ dài mảng của JVM trước mức đó.

### 2.2. Chứng minh bằng bất biến vòng lặp

Đặt `C[0..k)` là đoạn kết quả đã ghi. Tại đầu mỗi lần lặp chính, duy trì ba bất biến:

1. `C[0..k)` chứa **chính xác** các phần tử đã tiêu thụ: `A[0..i)` và `B[0..j)` (tính cả số lần xuất hiện); luôn có `k=i+j`.
2. `C[0..k)` đã sắp xếp không giảm.
3. Nếu prefix không rỗng, mọi phần tử chưa lấy trong cả hai dãy đều lớn hơn hoặc bằng phần tử cuối prefix.

**Khởi tạo:** `i=j=k=0`. Prefix rỗng, chưa tiêu thụ gì; mọi mệnh đề đúng.

**Bảo toàn:** khi cả hai dãy còn phần tử, `A[i]` và `B[j]` là các phần tử nhỏ nhất của hai phần còn lại. Chọn giá trị nhỏ hơn bảo đảm giá trị thêm vào không nhỏ hơn phần tử cuối prefix, đồng thời không bỏ/nhân đôi phần tử. Chỉ một con trỏ nguồn và `k` tăng đúng một lần. Bất biến tiếp tục đúng.

**Kết thúc vòng chính:** ít nhất một dãy đã hết. Dãy còn lại có thứ tự, và các giá trị còn lại đều không nhỏ hơn prefix đã ghi, nên chép toàn bộ đuôi giữ đúng ba tính chất. Khi hoàn tất, `k=m+n`, do đó kết quả vừa có thứ tự vừa chứa đầy đủ đa tập đầu vào.

**Tính dừng:** tổng số phần tử chưa lấy `(m-i)+(n-j)` giảm đúng một sau mỗi lần ghi; từ số nguyên không âm nên cuối cùng về `0`. Các vòng chép đuôi cũng tiến con trỏ tới giới hạn hữu hạn.

**Ổn định:** khi hai phần tử có khóa bằng nhau, điều kiện `<=` chọn A trước B; thứ tự từng nguồn không bị đảo vì mọi con trỏ chỉ tiến. Do đó kết quả ổn định so với cách đặt các phần tử A trước B khi hòa.

### 2.3. Độ phức tạp và giới hạn tối ưu

- **Thời gian:** `O(m+n)`. Mỗi phần tử được ghi **đúng một lần**, mỗi bước tiến một trong hai con trỏ. Nếu cả hai dãy không rỗng, vòng chính thực hiện tối đa `m+n-1` lần so sánh khóa.
- **Bộ nhớ phụ:** `O(m+n)` nếu cần cấp phát mảng kết quả độc lập; biến chỉ số ngoài mảng là `O(1)`.
- **Cận dưới xuất kết quả:** nếu phải **tạo mảng mới đủ m+n phần tử**, riêng việc ghi các phần tử đã cần `Ω(m+n)` thao tác. Vì vậy thời gian `O(m+n)` là tối ưu tiệm cận trong mô hình này.
- **Nếu đầu ra là luồng/iterator:** có thể phát từng phần tử mà không lưu toàn bộ kết quả, chỉ giữ hai phần tử đầu chưa lấy và trạng thái đọc, đạt **O(1)** bộ nhớ xử lý ngoài bộ đệm I/O.
- **Nếu cả hai mảng đã có trong RAM:** không thể nói “merge luôn dùng O(1) bộ nhớ” khi đang cấp phát `result` dài `m+n`; phải phân biệt vùng đầu ra và bộ nhớ bổ sung.

Không dùng `Arrays.sort(concat)` như một bước “merge”; việc sắp xếp lại bỏ qua lợi thế thứ tự có sẵn và thường có chi phí cao hơn. `Arrays.sort` vẫn có ích khi dữ liệu đầu vào **chưa** được sắp xếp — đó là bài toán khác.

## 3. Trộn ổn định các bản ghi có khóa bằng nhau

Với các số nguyên, hai giá trị `1` trông giống nhau nên khó nhìn thấy lỗi ổn định. Với bản ghi có khóa và nhãn riêng, ta kiểm chứng được thứ tự khi nhiều bản ghi có cùng khóa.

Lưu thành **StableRecordMerge.java**:

```java
import java.util.Arrays;

public class StableRecordMerge {
    record Event(int time, String id) {
        @Override
        public String toString() {
            return time + ":" + id;
        }
    }

    // Hai dãy đã sắp xếp không giảm theo Event.time().
    static Event[] merge(Event[] a, Event[] b) {
        Event[] result = new Event[a.length + b.length];
        int i = 0;
        int j = 0;
        int k = 0;

        while (i < a.length && j < b.length) {
            // Khi cùng time, Event của a được lấy trước.
            if (a[i].time() <= b[j].time()) {
                result[k++] = a[i++];
            } else {
                result[k++] = b[j++];
            }
        }
        while (i < a.length) {
            result[k++] = a[i++];
        }
        while (j < b.length) {
            result[k++] = b[j++];
        }
        return result;
    }

    public static void main(String[] args) {
        Event[] a = {
            new Event(1, "A1"),
            new Event(2, "A2"),
            new Event(2, "A3"),
            new Event(4, "A4")
        };
        Event[] b = {
            new Event(1, "B1"),
            new Event(2, "B2"),
            new Event(3, "B3")
        };

        System.out.println(Arrays.toString(merge(a, b)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StableRecordMerge.java
java StableRecordMerge
```

Stdout:

```text
[1:A1, 1:B1, 2:A2, 2:A3, 2:B2, 3:B3, 4:A4]
```

Ở khóa `2`, hai bản ghi `A2`, `A3` giữ nguyên thứ tự và đều đứng trước `B2`. Nếu đổi `<=` thành `<`, các bản ghi B cùng khóa có thể đi trước bản ghi A tương ứng, khiến kết quả không còn ổn định so với phép nối `A` rồi `B`.

**Với kiểu tổng quát:** thay so sánh số nguyên bằng `Comparator<? super T>` có tính nhất quán và thứ tự bắc cầu. Để ổn định, dùng `comparator.compare(a[i], b[j]) <= 0`. Không nên viết `a.time() - b.time() <= 0` cho dữ liệu số nguyên tùy ý vì phép trừ có thể bị tràn, làm đảo thứ tự so sánh.

Nếu muốn kết quả sắp xếp **giảm dần**, dãy nguồn cũng phải giảm dần, và phép chọn đầu phải chọn phần tử **lớn hơn** (ví dụ `>=` cho các số), hoặc dùng comparator giảm dần xuyên suốt. Đổi mỗi phép so sánh trong hàm mà không đổi tiền điều kiện là sai.

## 4. Trộn ngay trong mảng thứ nhất: đi từ cuối về đầu

Đôi khi mảng `A` đã có sẵn chỗ trống cuối để chứa cả hai dãy. Ví dụ:

```text
first  = [1, 3, 5, _, _, _]   m = 3, dung lượng 6
second = [2, 5, 6]            n = 3

Kết quả cần có ngay trong first:
[1, 2, 3, 5, 5, 6]
```

Nếu trộn từ **đầu mảng thứ nhất** vào chính mảng đó, ta có thể ghi đè phần tử của A chưa đọc. Cách hiệu quả là làm **ngược từ phải sang trái**:

- `i = m-1`: phần tử hợp lệ cuối cùng của A;
- `j = n-1`: phần tử cuối của B;
- `k = m+n-1`: ô đích cuối của A.

Ở mỗi bước chọn **phần tử lớn hơn** để đặt vào `first[k]`, rồi lùi con trỏ tương ứng. Khi bằng nhau, ưu tiên đặt phần tử của **B** vào ô sau cùng để bảo toàn thứ tự `A` trước `B` trong kết quả cuối cùng.

### 4.1. Ví dụ Java 17: merge vào vùng đệm sẵn có

Lưu thành **MergeIntoFirst.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class MergeIntoFirst {
    // first có đúng m phần tử hợp lệ đầu và n ô trống cuối.
    // second có n phần tử, là một mảng độc lập.
    static void mergeIntoFirst(int[] first, int m, int[] second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");
        if (m < 0 || m > first.length
                || first.length - m != second.length) {
            throw new IllegalArgumentException("Invalid capacity or m");
        }

        int i = m - 1;
        int j = second.length - 1;
        int k = first.length - 1;

        // Nếu second hết, phần còn lại của first đã ở đúng vị trí.
        while (j >= 0) {
            if (i >= 0 && first[i] > second[j]) {
                first[k--] = first[i--];
            } else {
                first[k--] = second[j--];
            }
        }
    }

    public static void main(String[] args) {
        int[] first = {1, 3, 5, 0, 0, 0};
        int[] second = {2, 5, 6};
        mergeIntoFirst(first, 3, second);
        System.out.println(Arrays.toString(first));

        int[] emptyPrefix = {0, 0};
        mergeIntoFirst(emptyPrefix, 0, new int[]{-2, 7});
        System.out.println(Arrays.toString(emptyPrefix));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MergeIntoFirst.java
java MergeIntoFirst
```

Stdout:

```text
[1, 2, 3, 5, 5, 6]
[-2, 7]
```

**Vì sao không ghi đè phần tử chưa đọc?** Trong khi còn phần tử ở B (`j>=0`), chỉ số ghi `k=i+j+1`, nên `k>i`. Mọi phép ghi vào `first[k]` đều nằm sau các phần tử gốc của A chưa xử lý. Nếu B hết, các phần tử A còn lại đã nằm đúng vị trí, nên có thể dừng.

**Bất biến theo hướng ngược:** đoạn `first[k+1..m+n)` chứa đúng các phần tử **lớn nhất đã chọn** của hai dãy, theo thứ tự không giảm ở phía đích. Phần chưa xử lý còn nằm trong `first[0..i]` và `second[0..j]`. Chọn phần tử lớn hơn của hai đuôi bảo toàn bất biến; khi hai khóa bằng nhau, đặt B sau A duy trì ổn định theo quy ước A trước B.

**Chi phí:** `O(m+n)` thời gian, **O(1)** bộ nhớ phụ vì dùng chính các ô đích đã cấp sẵn. Hàm **làm thay đổi** `first`. Hai dãy phải được sắp xếp; `second` phải là vùng dữ liệu độc lập với `first` để không bị ghi đè ngoài ý muốn.

Các ô dự trữ cuối `first` không cần chứa số `0`; chúng **không phải dữ liệu đầu vào**. Trong ví dụ dùng `0` chỉ vì Java khởi tạo mảng số nguyên mặc định bằng `0`.

**Nếu mảng nguồn thứ nhất không có chỗ trống:** không thể dùng nguyên phương pháp này mà không cấp thêm chỗ hoặc dịch chuyển dữ liệu. Các thuật toán trộn tại chỗ hoàn toàn tồn tại nhưng phức tạp hơn; lựa chọn `O(m+n)` thời gian với vùng đệm đầu ra thường đơn giản và đáng tin hơn.

## 5. Trộn k dãy đã sắp xếp

Cho `k` dãy, với tổng số phần tử `N`. Hai cách cơ bản:

1. **Trộn lần lượt:** lấy dãy 1 và 2 trộn, rồi trộn kết quả với dãy 3, ... Cách này đơn giản nhưng có thể tốn `O(kN)` thao tác trong trường hợp xấu do các phần tử ở kết quả tích lũy bị sao chép lặp lại.
2. **Trộn cân bằng hoặc dùng hàng đợi ưu tiên:** tận dụng cấu trúc để giảm số lần một phần tử phải được xét, thường đạt `O(N log k)` cho `k>=2`.

### 5.1. K-way merge với min-heap

Giữ **nhiều nhất một phần tử đầu chưa lấy của mỗi dãy** trong một min-heap. Mỗi phần tử heap gồm giá trị và chỉ số nguồn.

Quy trình:

1. Đưa phần tử đầu của mỗi dãy **không rỗng** vào heap.
2. Lấy phần tử nhỏ nhất khỏi heap và ghi vào kết quả.
3. Từ cùng dãy nguồn, đưa **phần tử tiếp theo** vào heap nếu còn.
4. Lặp cho tới khi heap rỗng.

Vì mỗi dãy đã sắp xếp, phần tử nhỏ nhất chưa lấy của một dãy luôn là đầu hiện tại. Min-heap lưu tất cả các đầu đó nên phần tử lấy ra là nhỏ nhất **trên mọi dãy còn lại**.

Để kết quả ổn định so với phép nối `dãy 0`, `dãy 1`, ..., `dãy k-1`, khi **giá trị bằng nhau** dùng chỉ số nguồn nhỏ hơn làm khóa phụ. Trong mỗi nguồn, ta chỉ đưa phần tử kế tiếp vào heap sau khi lấy phần tử trước, nên thứ tự nội bộ được giữ nguyên.

### 5.2. Java 17: trộn nhiều dãy bằng heap và Iterator

Lưu thành **KWayMergeDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.PriorityQueue;

public class KWayMergeDemo {
    record Head(int value, int source) {}

    static List<Integer> merge(List<List<Integer>> streams) {
        // Heap ưu tiên giá trị nhỏ hơn, rồi nguồn có chỉ số nhỏ hơn.
        PriorityQueue<Head> heap = new PriorityQueue<>(
            Comparator.comparingInt(Head::value)
                      .thenComparingInt(Head::source)
        );

        List<Iterator<Integer>> iterators = new ArrayList<>();
        int source = 0;
        for (List<Integer> stream : streams) {
            Iterator<Integer> iterator = stream.iterator();
            iterators.add(iterator);
            if (iterator.hasNext()) {
                heap.add(new Head(iterator.next(), source));
            }
            source++;
        }

        List<Integer> result = new ArrayList<>();
        while (!heap.isEmpty()) {
            Head head = heap.remove();
            result.add(head.value());

            Iterator<Integer> from = iterators.get(head.source());
            if (from.hasNext()) {
                heap.add(new Head(from.next(), head.source()));
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<List<Integer>> streams = List.of(
            List.of(1, 4, 9),
            List.of(1, 3, 10),
            List.of(),
            List.of(2, 6)
        );
        System.out.println("Merged: " + merge(streams));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KWayMergeDemo.java
java KWayMergeDemo
```

Stdout:

```text
Merged: [1, 1, 2, 3, 4, 6, 9, 10]
```

**Giả thiết:** mỗi danh sách nguồn được sắp xếp không giảm, không có phần tử `null`; danh sách nguồn không bị sửa đồng thời trong lúc duyệt. Sử dụng `Iterator` giúp duyệt được cả `ArrayList` lẫn `LinkedList` mà không gọi liên tục `get(i)` trên danh sách liên kết.

**Tính đúng:** trước mỗi lần lấy heap, heap chứa **chính xác một phần tử đầu chưa tiêu thụ** của mỗi nguồn còn dữ liệu. Min của heap bằng min của toàn bộ dữ liệu chưa lấy, nên thêm nó vào kết quả giữ thứ tự. Sau khi lấy, việc thay bằng đầu tiếp theo của chính nguồn đó tái lập bất biến. Mỗi phần tử nguồn được đưa vào và lấy khỏi heap đúng một lần; khi heap rỗng thì tất cả đã được ghi.

**Chi phí:** heap có không quá `k` phần tử. Với `k>=2`, mỗi lần `remove`/`add` mất `O(log k)`, tổng thời gian `O(k + N log k)` nếu kể bước khởi tạo và duyệt danh sách nguồn. Bộ nhớ xử lý **O(k)** cho heap và các iterator, ngoài **O(N)** để giữ danh sách kết quả. Với `k=0`, kết quả rỗng; với `k=1`, thuật toán đơn giản duyệt dãy duy nhất trong `O(N)`. Nếu xuất từng phần tử trực tiếp thay vì thêm vào `result`, có thể tránh phần bộ nhớ `O(N)` cho kết quả.

**Lưu ý với luồng thật:** ví dụ lưu `List<Integer>` trong RAM để dễ chạy. Với dữ liệu đọc từ tệp hoặc API, có thể thay Iterator bằng bộ đọc có đệm và giữ phần tử hiện tại của từng nguồn, rồi ghi lần lượt ra đích. Khi đó chi phí bộ nhớ làm việc phụ thuộc kích thước bộ đệm của `k` nguồn, không cần giữ tất cả `N` phần tử trong RAM.

### 5.3. Trộn k dãy theo chia để trị

Một lựa chọn khác là chia `k` dãy thành hai nhóm, trộn đệ quy mỗi nhóm rồi trộn hai kết quả bằng thuật toán hai con trỏ. Hình dung cây trộn cân bằng:

```text
Dãy 0 ──┐
        ├─ merge ──┐
Dãy 1 ──┘          │
                   ├─ merge ── kết quả
Dãy 2 ──┐          │
        ├─ merge ──┘
Dãy 3 ──┘
```

Ở mỗi tầng cây cân bằng, mỗi phần tử đi qua nhiều nhất một lần trộn. Có `O(log k)` tầng nên thời gian `O(N log k)` với `k>=2`. Cách này hợp với **xử lý theo lô** và dễ tận dụng chiến lược trộn hai dãy đã có. Heap hợp với **luồng nhiều nguồn** vì chỉ cần duy trì phần tử đầu của mỗi nguồn.

**Không phải lúc nào trộn lần lượt cũng tốn đúng `kN`:** đó là chặn xấu điển hình; khi các dãy có kích thước rất lệch hoặc nhiều dãy rỗng, chi phí thực tế khác. Hãy tính theo tổng số phần tử được đọc/ghi ở từng lượt.

## 6. Trộn khác gì với hợp, giao và hiệu hai tập đã sắp xếp?

Hai con trỏ còn phục vụ nhiều bài toán trên dãy có thứ tự, nhưng **ngữ nghĩa đầu ra khác nhau**.

| Bài toán | Xử lý khi `A[i] == B[j]` | Có giữ giá trị trùng không? |
|---|---|---|
| **Merge hai dãy** | Chọn một nguồn, rồi nguồn còn lại sẽ được chọn ở bước sau | **Có**, giữ mọi lần xuất hiện |
| **Hợp hai tập** (*set union*) | Ghi giá trị một lần, bỏ các bản sao của cả hai phía | Không, chỉ một lần mỗi giá trị |
| **Giao hai tập** (*set intersection*) | Ghi giá trị chung một lần, bỏ các bản sao | Không, chỉ các giá trị chung |
| **Hiệu tập** `A \ B` | Bỏ giá trị khỏi A nếu cũng xuất hiện trong B | Không, chỉ giữ giá trị có ở A mà không ở B |
| **Giao hai đa tập** (*multiset intersection*) | Ghi số lần bằng `min(countA,countB)` | Có, nhưng chỉ theo số lần tối thiểu |

Ví dụ:

```text
A = [1, 1, 2, 5, 5]
B = [1, 3, 5, 5, 7]

Merge (giữ tất cả): [1, 1, 1, 2, 3, 5, 5, 5, 5, 7]
Hợp tập:            [1, 2, 3, 5, 7]
Giao tập:           [1, 5]
Hiệu tập A \ B:     [2]
Giao đa tập:        [1, 5, 5]
```

Với các phép tập hợp loại trùng, hai con trỏ phải **bỏ qua toàn bộ đoạn các giá trị bằng nhau** sau khi xử lý mỗi giá trị; chỉ tăng `i` và `j` mỗi bên một lần có thể làm kết quả còn trùng hoặc thiếu. Với merge thuần túy, **không được tự động bỏ phần tử trùng**, vì như thế làm thay đổi dữ liệu.

### 6.1. Mẫu hai con trỏ cho giao hai tập (không lặp)

Đoạn mã sau là **minh họa** bên trong một phương thức (không phải chương trình Java độc lập):

```java
List<Integer> result = new ArrayList<>();
int i = 0, j = 0;

while (i < a.length && j < b.length) {
    int x = a[i], y = b[j];
    if (x < y) {
        while (i < a.length && a[i] == x) i++;
    } else if (x > y) {
        while (j < b.length && b[j] == y) j++;
    } else {
        result.add(x);
        while (i < a.length && a[i] == x) i++;
        while (j < b.length && b[j] == y) j++;
    }
}
```

Giả sử `a`, `b` đều được sắp xếp không giảm. Mỗi con trỏ chỉ tiến, không lùi, nên thời gian vẫn `O(m+n)`. Đoạn này dùng `java.util.List`, `java.util.ArrayList` và hai mảng `int[] a`, `int[] b` đã khai báo ở ngữ cảnh bên ngoài.

## 7. Liên hệ với merge sort, linked list và dữ liệu lớn

### 7.1. Merge sort dựa vào phép trộn

**Merge sort** chia mảng thành hai nửa, sắp xếp đệ quy hai nửa, rồi gọi merge trên **hai đoạn đã sắp xếp**. Nếu bước ghép tốn `O(n)`, truy hồi điển hình là:

`T(n) = T(floor(n/2)) + T(ceil(n/2)) + O(n)`

suy ra `O(n log n)` thời gian. Mỗi lời gọi con phải trả đúng thứ tự; nếu một nửa còn lộn xộn, merge không thể bảo đảm sắp xếp toàn đoạn.

Một cách chứng minh merge sort là quy nạp theo độ dài: đoạn rỗng/một phần tử có thứ tự; giả thiết hai nửa đã được sắp xếp đúng; thuật toán merge (đã chứng minh độc lập) tạo đoạn đã sắp xếp, bảo toàn mọi phần tử. Nếu chọn từ nửa trái khi các khóa bằng nhau, merge sort có thể **ổn định** khi tất cả bước trộn tuân thủ quy tắc đó.

### 7.2. Trộn hai danh sách liên kết đã sắp xếp

Với hai singly linked list đã sắp xếp, thuật toán hai con trỏ vẫn đúng. Thay vì mảng kết quả, ta có thể nối lại liên kết của các node, sử dụng một **đầu giả** (*dummy head*) và con trỏ `tail`.

- So sánh giá trị của hai node đầu chưa lấy; nối node nhỏ hơn vào `tail.next`.
- Dịch con trỏ ở danh sách nguồn vừa chọn, rồi dịch `tail`.
- Khi một danh sách hết, nối nguyên chuỗi còn lại.

Cần xác nhận hai danh sách **không giao nhau về danh tính node**, không có chu trình, và cho phép **sửa liên kết**. Khi thỏa điều kiện, thời gian `O(m+n)`, bộ nhớ phụ `O(1)` ngoài các node đã có. Nếu phải giữ nguyên hai danh sách nguồn, cần tạo node kết quả mới hoặc dùng cách bất biến; không thể đồng thời nối lại node nguồn và cam kết nguồn không đổi.

**Không dùng `list.get(i)` liên tục trên `LinkedList`:** mỗi lần truy cập theo chỉ số có thể phải đi qua nhiều node. Hai iterator hoặc hai con trỏ node giữ được thời gian tuyến tính.

### 7.3. Trộn tệp hoặc luồng đã sắp xếp (*external merge*)

Khi dữ liệu không vừa trong RAM, ta có thể giữ **bộ đệm đọc** cho mỗi tệp và một **bộ đệm ghi** cho đầu ra. Trộn hai tệp chỉ cần nhìn phần tử đầu đang chờ ở hai nguồn, chọn phần tử nhỏ hơn rồi đọc tiếp ở nguồn tương ứng. Không cần nạp tất cả dữ liệu vào RAM.

Với nhiều tệp, min-heap giữ một bản ghi hiện tại của mỗi tệp. Đây là nền tảng của **external merge sort**, nơi dữ liệu đầu tiên được chia thành các *run* đã sắp xếp, rồi trộn qua một hoặc nhiều lượt.

Nếu đọc/ghi theo khối gồm `B` phần tử, riêng trộn tuần tự hai tệp có khoảng `O(N/B)` lượt I/O khối trong mô hình lý tưởng, ngoài chi phí mở/đóng tệp và cấp phát bộ đệm. Trộn `k` tệp một lượt cần đủ RAM cho các bộ đệm đầu vào và đầu ra; nếu `k` quá lớn thì phải trộn nhiều lượt. Cũng cần quy định rõ **khóa sắp xếp**, cách xử lý bản ghi trùng và thứ tự nguồn khi yêu cầu ổn định.

Ứng dụng: gộp log đã sắp theo timestamp, trộn các run của external sort, hợp nhất các stream sự kiện, tạo danh sách đã sắp xếp từ nhiều phân vùng, hay bước `merge` trong truy vấn cơ sở dữ liệu sau khi hai nguồn có khóa phù hợp.

**Phân biệt với “trộn khoảng”:** bài toán *merge overlapping intervals* thường sắp xếp các khoảng theo điểm bắt đầu rồi hợp nhất những khoảng giao nhau. Dù có chữ *merge*, nó có ngữ nghĩa khác bài toán giữ đầy đủ phần tử của các dãy đã sắp xếp.

## 8. Các lỗi cài đặt dễ mắc

### 8.1. Sai điều kiện dừng hoặc làm mất phần đuôi

Nếu dừng ngay khi một nguồn hết mà **không sao chép phần còn lại** của nguồn kia, đầu ra thiếu dữ liệu. Cần xử lý cả hai vòng chép đuôi. Có thể chỉ có một trong hai vòng thật sự chạy.

### 8.2. Tăng sai con trỏ

Sau khi lấy từ `A`, chỉ tăng `i`; sau khi lấy từ `B`, chỉ tăng `j`. `k` luôn tăng đúng một lần khi ghi phần tử. Nhầm tăng cả `i` và `j` sẽ bỏ sót dữ liệu; quên tăng sẽ lặp vô hạn.

### 8.3. Không duy trì cùng comparator

Hai nguồn phải đã sắp theo **cùng thứ tự** với cách chọn phần tử trong merge. Nếu A tăng, B giảm mà dùng `<=`, bất biến “đầu nguồn là phần tử nhỏ nhất còn lại” không đúng.

### 8.4. Bỏ trùng ngoài yêu cầu

Merge chuẩn bảo toàn **mọi lần xuất hiện**, không giống phép hợp tập hợp. Nếu đầu vào chứa bốn giá trị `5` tổng cộng, kết quả merge cũng phải chứa bốn giá trị `5`.

### 8.5. Mất ổn định khi bằng khóa

Với dữ liệu bản ghi, dùng `<` thay `<=` sẽ thay đổi thứ tự bản ghi từ hai nguồn khi khóa hòa. Nếu nghiệp vụ yêu cầu ổn định, quy ước nguồn ưu tiên phải nhất quán.

### 8.6. Ghi đè phần tử chưa đọc khi merge tại chỗ

Nếu A chứa `m` phần tử thật và `n` ô dự trữ phía sau, cần trộn **từ cuối**, hoặc dùng bộ đệm đủ lớn. Trộn trực tiếp từ đầu vào cùng mảng có thể phá dữ liệu A đang chờ đọc.

### 8.7. Nhầm giá trị dự trữ với dữ liệu

`first = [1,3,5,0,0,0]` với `m=3` nghĩa là chỉ ba phần tử đầu thuộc nguồn A. Ba số `0` cuối là **vùng nhớ trống**, không được tự coi là giá trị thật. Kích thước hợp lệ `m` là một phần của đầu vào.

### 8.8. So sánh bằng phép trừ có nguy cơ tràn

Đừng viết `return a - b` khi triển khai comparator cho số nguyên tùy ý. Với giá trị gần `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, phép trừ có thể tràn khiến comparator sai. Dùng `Integer.compare(a,b)` hoặc `Comparator.comparingInt(...)`.

### 8.9. Nhầm độ phức tạp của heap và đầu ra

K-way merge dùng heap `O(k)` bộ nhớ xử lý, **nhưng** nếu lưu tất cả vào `ArrayList`, vẫn cần thêm `O(N)` bộ nhớ đầu ra. Nếu dữ liệu vào dạng `LinkedList` mà gọi `get(index)` từng phần tử, thời gian có thể bị phá hỏng; dùng iterator hoặc con trỏ node.

### 8.10. Giả định dữ liệu đã sắp xếp mà không ghi hợp đồng

Các phương thức mẫu giả thiết dữ liệu đã sắp xếp; chúng không tự kiểm tra điều này để không thêm lần quét kiểm tra. Ở API công khai, hãy tài liệu hóa tiền điều kiện hoặc xác thực nếu yêu cầu ưu tiên an toàn hơn chi phí.

## 9. Bộ ca kiểm thử có chủ đích

Các trường hợp sau giúp phát hiện lỗi biên và lỗi ngữ nghĩa:

| A | B | Kết quả merge mong đợi | Điều cần kiểm tra |
|---|---|---|---|
| `[]` | `[]` | `[]` | Hai nguồn rỗng |
| `[]` | `[2,2]` | `[2,2]` | Một nguồn rỗng; giữ trùng |
| `[1]` | `[]` | `[1]` | Chép đuôi A |
| `[1,2]` | `[3,4]` | `[1,2,3,4]` | Hai miền tách rời |
| `[3,4]` | `[1,2]` | `[1,2,3,4]` | Nguồn B nhỏ hơn toàn A |
| `[-4,-1,8]` | `[-2,0]` | `[-4,-2,-1,0,8]` | Số âm và dương |
| `[1,1,3]` | `[1,2,3]` | `[1,1,1,2,3,3]` | Bảo toàn số lần trùng |
| `[5,5]` | `[5,5]` | `[5,5,5,5]` | Tất cả khóa bằng nhau |
| `[1,7]` | `[2,3,4,5,6]` | `[1,2,3,4,5,6,7]` | Kích thước rất lệch |

Với bản ghi có nhãn, phải kiểm tra **thứ tự các nhãn** khi khóa bằng nhau, vì kiểm tra mảng số nguyên không phát hiện được sự thiếu ổn định.

Có thể xây một **oracle để kiểm thử** bằng cách nối hai mảng, sắp xếp bản sao rồi so sánh với output merge. Oracle không phải giải pháp được ưu tiên về độ phức tạp, nhưng hữu ích để tìm lỗi trong thuật toán mới qua dữ liệu nhỏ/ngẫu nhiên. Đồng thời kiểm tra tổng số phần tử và tần suất từng giá trị.

**Một vài bất biến có thể tự động kiểm tra trên kết quả:**

- `result.length == a.length + b.length`.
- Với mọi chỉ số `t>0`, `result[t-1] <= result[t]`.
- `count(result, x) == count(a,x) + count(b,x)` cho mỗi giá trị `x`.
- Với bản ghi, danh sách ID của các phần tử từ cùng một nguồn xuất hiện theo đúng thứ tự gốc.
- Với quy ước A trước B, nếu khóa bằng nhau xuyên nguồn thì bản ghi A phải đứng trước B.

Các kiểm tra này giúp phát hiện lỗi, còn chứng minh bằng bất biến ở phần 2 cho bảo đảm tổng quát khi tiền điều kiện được thỏa mãn.

## 10. Bài tập vận dụng

### Bài 1: Trộn giảm dần

Cho `A=[9,7,1]`, `B=[8,6,1]`, cả hai đã sắp giảm dần. Hãy chỉnh quy tắc so sánh và nêu kết quả.

**Đáp án:** chọn phần tử **lớn hơn** từ hai đầu, ưu tiên A khi bằng nhau (`>=`). Kết quả `[9,8,7,6,1,1]`. Nếu dùng `<=` của phiên bản tăng dần, kết quả không đảm bảo sắp giảm.

### Bài 2: Kiểm tra ổn định

Cho `A=[(2,A1),(2,A2)]`, `B=[(2,B1)]`. Quy tắc nào tạo kết quả ổn định so với phép nối A rồi B?

**Đáp án:** nếu khóa bằng nhau, chọn từ A (`<=` khi so sánh khóa). Kết quả `[(2,A1),(2,A2),(2,B1)]`. Quy tắc chọn B khi hòa không thỏa yêu cầu này.

### Bài 3: Mảng đã cấp phát dư

Cho `first=[2,4,9,0,0]`, `m=3`, `second=[1,10]`. Trộn tại chỗ đúng cách cho kết quả gì?

**Đáp án:** `[1,2,4,9,10]`. Dùng ba con trỏ ở cuối để tránh ghi đè các giá trị A chưa đọc.

### Bài 4: Nhiều dãy

Có `k=100` dãy đã sắp xếp với tổng `N=1_000_000` phần tử. Nếu chỉ cần xuất lần lượt, nên cân nhắc gì?

**Gợi ý:** min-heap giữ đầu của mỗi nguồn, chi phí xấp xỉ `O(N log k)` và bộ nhớ xử lý `O(k)` cộng các bộ đệm. Không cần giữ cả triệu phần tử ở một mảng kết quả nếu đầu ra có thể ghi trực tiếp.

### Bài 5: Chỉ lấy các phần tử chung

Cho `A=[1,1,2,5,5]`, `B=[1,3,5,5,7]`. Nếu đề yêu cầu **giao của hai tập giá trị phân biệt**, kết quả là gì? Nó khác merge thế nào?

**Đáp án:** giao tập là `[1,5]`; merge đầy đủ là `[1,1,1,2,3,5,5,5,5,7]`. Bài giao tập dùng hai con trỏ nhưng bỏ lặp và chỉ ghi giá trị xuất hiện ở cả hai.

## 11. Quy trình chọn biến thể phù hợp

1. **Đầu vào đã thật sự có thứ tự chưa?** Cùng chiều, cùng comparator, cùng cách xử lý `null` và khóa trùng?
2. **Đề yêu cầu giữ đầy đủ từng bản ghi hay chỉ giữ giá trị phân biệt?** Merge chuẩn giữ **mọi** lần xuất hiện.
3. **Có yêu cầu ổn định không?** Nếu có, xác định nguồn ưu tiên khi hòa và giữ thứ tự nội bộ nguồn.
4. **Có bao nhiêu dãy?** Hai dãy → hai con trỏ. Nhiều dãy → heap hoặc merge cân bằng.
5. **Đầu ra nằm ở đâu?** Mảng mới `O(m+n)` bộ nhớ đầu ra; mảng thứ nhất có vùng đệm → merge ngược `O(1)` bộ nhớ phụ; stream → xuất dần.
6. **Dạng dữ liệu gì?** Mảng có truy cập chỉ số `O(1)`; linked list/stream hợp với iterator hoặc con trỏ node.
7. **Giới hạn hệ thống:** kiểm tra độ dài đầu ra, tổng dữ liệu, bộ nhớ JVM, I/O nếu trộn tệp lớn.
8. **Chứng minh và kiểm thử:** bất biến prefix (hoặc suffix khi merge ngược), tiêu thụ đủ phần tử, xử lý hết đuôi, trường hợp hòa/biên.

**Ghi nhớ:** trộn các dãy đã có thứ tự tận dụng một quan sát mạnh: **phần tử nhỏ nhất chưa lấy của mỗi dãy luôn ở đầu phần chưa xử lý**. Hai con trỏ đủ cho hai nguồn; min-heap hoặc cây trộn mở rộng lên nhiều nguồn. Tính đúng đòi hỏi đồng thời **có thứ tự**, **giữ đúng đa tập phần tử** và **ổn định khi được yêu cầu**.
