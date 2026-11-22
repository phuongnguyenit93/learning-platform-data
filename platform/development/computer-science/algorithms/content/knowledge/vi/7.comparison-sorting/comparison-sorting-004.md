# Sắp xếp chèn (insertion sort)

> **Chủ đề:** Computer Science Algorithms → Sắp xếp so sánh.  
> **Mục tiêu:** Hiểu cơ chế sắp xếp chèn, tự lần theo từng bước, chứng minh tính đúng và ổn định, tính được thời gian/bộ nhớ trong các trường hợp, và biết khi nào dùng insertion sort hay các biến thể trong Java 17+.

## 1. Sắp xếp chèn là gì?

**Insertion sort** là thuật toán sắp xếp so sánh xây dựng một **đoạn đầu đã có thứ tự** (*sorted prefix*) của dãy. Ở mỗi lượt, thuật toán lấy phần tử tiếp theo, tìm vị trí phù hợp trong đoạn đã có thứ tự, dịch các phần tử lớn hơn sang phải rồi **chèn** phần tử đó vào khoảng trống.

Hình dung cách sắp xếp các lá bài trên tay: giữ các lá bài bên trái có thứ tự; lấy lá mới, lùi dần qua các lá lớn hơn rồi đặt nó vào vị trí đúng.

Giả sử cần sắp xếp mảng theo thứ tự **không giảm**:

```text
Ban đầu: [5, 2, 4, 6, 1, 3]
          ^
          Đoạn [5] đã có thứ tự.

Lấy 2:   [2, 5, 4, 6, 1, 3]
Lấy 4:   [2, 4, 5, 6, 1, 3]
Lấy 6:   [2, 4, 5, 6, 1, 3]
Lấy 1:   [1, 2, 4, 5, 6, 3]
Lấy 3:   [1, 2, 3, 4, 5, 6]
```

Trong mỗi dòng, đoạn đã được xử lý kéo dài thêm một phần tử. Ở dòng cuối, đoạn đã xử lý là toàn bộ mảng.

**Điều kiện đầu vào:** insertion sort không yêu cầu mảng đã có thứ tự. Điều kiện là các phần tử có **quan hệ so sánh nhất quán**: với số nguyên, dùng `<` hoặc `>`; với đối tượng, dùng `Comparator` tạo thứ tự phù hợp.

**Kết quả đúng** cần hai tính chất: (1) mảng được sắp theo thứ tự yêu cầu; (2) mảng chứa đúng **đa tập** phần tử ban đầu, kể cả các giá trị trùng. Nếu còn yêu cầu *ổn định*, thuật toán phải giữ nguyên thứ tự tương đối giữa các phần tử có khóa bằng nhau.

## 2. Thuật toán chuẩn: chèn bằng cách dịch phần tử

Gọi `a` là mảng dài `n`. Sau khi xử lý xong các vị trí từ `0` đến `i-1`, đoạn `a[0..i)` đã có thứ tự.

Ở bước `i`:

1. Lưu `key = a[i]`, tránh mất giá trị khi dịch.
2. Từ chỉ số `j = i-1`, so sánh `a[j]` với `key`.
3. Khi `a[j] > key`, dịch `a[j]` sang vị trí `j+1`, rồi lùi `j`.
4. Khi `j < 0` hoặc `a[j] <= key`, dừng và đặt `key` vào `a[j+1]`.
5. Đoạn `a[0..i+1)` lúc này có thứ tự, tiếp tục với `i+1`.

**Pseudocode:**

```text
INSERTION-SORT(a):
    for i = 1 to a.length - 1:
        key = a[i]
        j = i - 1
        while j >= 0 AND a[j] > key:
            a[j + 1] = a[j]
            j = j - 1
        a[j + 1] = key
```

Điều kiện `a[j] > key` là chi tiết thiết yếu:

- `>`: chỉ dịch các phần tử **lớn hơn hẳn** `key`; những phần tử **bằng** `key` nằm trước nó, nên bản chuẩn là **stable**.
- `>=`: dịch cả phần tử bằng `key`; dữ liệu vẫn có thứ tự nhưng có thể **đảo thứ tự của các bản ghi cùng khóa**, làm thuật toán không ổn định.

Ở Java, viết `j >= 0 && a[j] > key` theo **đúng thứ tự này** để `&&` ngắn mạch không truy cập `a[-1]`.

### 2.1. Java 17: cài đặt đầy đủ cho mảng `int[]`

Lưu thành **InsertionSortDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class InsertionSortDemo {
    static void insertionSort(int[] a) {
        Objects.requireNonNull(a, "a");

        for (int i = 1; i < a.length; i++) {
            int key = a[i];
            int j = i - 1;

            while (j >= 0 && a[j] > key) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = key;
        }
    }

    public static void main(String[] args) {
        int[] values = {5, 2, 4, 6, 1, 3};
        insertionSort(values);
        System.out.println("Sorted: " + Arrays.toString(values));

        int[] duplicates = {3, 1, 3, -2, 1};
        insertionSort(duplicates);
        System.out.println("Duplicates: " + Arrays.toString(duplicates));

        int[] empty = {};
        insertionSort(empty);
        System.out.println("Empty: " + Arrays.toString(empty));
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 InsertionSortDemo.java
java InsertionSortDemo
```

Stdout:

```text
Sorted: [1, 2, 3, 4, 5, 6]
Duplicates: [-2, 1, 1, 3, 3]
Empty: []
```

Hàm **thay đổi chính mảng đầu vào**, không tạo một mảng kết quả khác. `Objects.requireNonNull` từ chối `null`; mảng rỗng và mảng chỉ có một phần tử được xử lý tự nhiên vì vòng `for` không chạy.

### 2.2. Theo dõi một lượt chèn cụ thể

Giả sử trước lượt `i=4` của ví dụ trên:

```text
Mảng: [2, 4, 5, 6, 1, 3]
       └── prefix ─┘  key=1
```

Ta giữ `key=1`, rồi thực hiện:

```text
j=3: a[3]=6 > 1  → dịch 6 sang vị trí 4
       [2, 4, 5, 6, 6, 3]
j=2: a[2]=5 > 1  → dịch 5 sang vị trí 3
       [2, 4, 5, 5, 6, 3]
j=1: a[1]=4 > 1  → dịch 4 sang vị trí 2
       [2, 4, 4, 5, 6, 3]
j=0: a[0]=2 > 1  → dịch 2 sang vị trí 1
       [2, 2, 4, 5, 6, 3]
j=-1: dừng, ghi key tại a[0]
       [1, 2, 4, 5, 6, 3]
```

Trong quá trình dịch, mảng có thể tạm chứa **bản sao** của một giá trị, vì `key` đã được lưu riêng. Chỉ khi ghi `key` vào vị trí trống mới hoàn thành lượt chèn và khôi phục đúng đa tập ban đầu. Không được coi trạng thái giữa vòng `while` là kết quả sắp xếp cuối cùng.

## 3. Chứng minh tính đúng bằng bất biến vòng lặp

Dùng một bất biến tại **đầu mỗi lượt `for` với chỉ số `i`**:

> Đoạn `a[0..i)` đã sắp xếp không giảm và chứa đúng đa tập của các phần tử **ở những vị trí 0..i-1 của đầu vào ban đầu**; đoạn chưa xử lý `a[i..n)` vẫn chứa các phần tử gốc chưa xét.

Đây là mệnh đề mạnh hơn “prefix đã có thứ tự”, vì nếu một thuật toán chỉ thay các phần tử bằng giá trị nhỏ nhất thì cũng có thể làm prefix có thứ tự mà vẫn sai.

### 3.1. Khởi tạo

Ở lượt đầu, `i=1`; prefix chỉ có `a[0]`. Một dãy dài một phần tử luôn có thứ tự, bảo toàn chính phần tử đó. Các vị trí từ `1` trở đi chưa đổi nên bất biến đúng.

Với `n=0` hoặc `n=1`, vòng không chạy; toàn bộ mảng vốn đã có thứ tự và giữ nguyên dữ liệu, nên thuật toán đúng.

### 3.2. Bảo toàn

Giả sử trước lượt `i`, prefix `a[0..i)` đã có thứ tự. Ta lấy `key=a[i]`.

Vì prefix đã có thứ tự, các phần tử lớn hơn `key` ở **đuôi prefix** nằm liền nhau. Vòng `while` dịch từng phần tử lớn hơn sang phải. Nó dừng đúng trước vị trí của phần tử cuối cùng `<= key` (hoặc vượt qua đầu mảng). Sau đó:

- Mọi phần tử đứng **trước** `key` đều `<= key`.
- Mọi phần tử đứng **sau** `key` trong prefix mới đều `> key`.
- Thao tác dịch chỉ chuyển chỗ các phần tử cũ; việc lưu và ghi `key` bảo đảm không mất hoặc tạo thêm phần tử.
- Các vị trí từ `i+1` trở đi không bị sửa.

Vậy prefix `a[0..i+1)` có thứ tự và giữ đúng đa tập phần tử đầu vào của nó. Bất biến được bảo toàn.

### 3.3. Kết thúc và dừng

Khi vòng `for` kết thúc, `i=n`; bất biến suy ra toàn bộ `a[0..n)` có thứ tự và bảo toàn mọi phần tử đầu vào. Điều đó chứng minh **đúng bộ phận**.

Vòng ngoài đi từ `1` đến `n-1`. Trong một lượt `i`, biến `j` giảm đúng một ở mỗi vòng `while`, từ `i-1` xuống ít nhất `-1`. Vì các chỉ số bị chặn, cả hai vòng kết thúc hữu hạn, chứng minh **tính dừng**. Hai kết luận cho **tính đúng toàn phần**.

### 3.4. Chứng minh ổn định

Giả sử hai bản ghi khác nhau `x` và `y` có cùng khóa, `x` xuất hiện trước `y` trong dữ liệu gốc.

Khi chèn `y`, các bản ghi cùng khóa trong prefix **không bị dịch**, vì điều kiện vòng là `a[j] > key`, không phải `>=`. Do đó `y` được đặt sau những bản ghi bằng khóa đã có. Các lượt khác cũng không vượt qua hai bản ghi bằng khóa bằng cách dịch. Vì thế thứ tự tương đối của các bản ghi bằng khóa được bảo toàn.

**Lưu ý:** ổn định có nghĩa *giữ thứ tự tương đối của các bản ghi có khóa bằng nhau*; nếu chỉ sắp `int[]`, các giá trị bằng nhau không mang danh tính riêng nên không quan sát được tính chất này qua kết quả số.

## 4. Độ phức tạp: tốt nhất, trung bình, xấu nhất

Xét `n` phần tử.

| Trường hợp | Đầu vào điển hình | Số lần dịch | Thời gian |
|---|---|---|---|
| **Tốt nhất** | Mảng đã tăng không giảm | `0` | `Θ(n)` với `n>=1` |
| **Trung bình** | Hoán vị ngẫu nhiên của các khóa phân biệt | Trung bình `n(n-1)/4` | `Θ(n²)` |
| **Xấu nhất** | Mảng giảm nghiêm ngặt | `n(n-1)/2` | `Θ(n²)` |

Với `n=0` hoặc `n=1`, thời gian hằng số. Bảng dùng phân tích theo số phép so sánh/dịch cơ bản; chi phí hằng của JVM và cache phần cứng không thay đổi bậc tiệm cận.

### 4.1. Vì sao mảng đã sắp xếp chạy nhanh?

Ở mỗi lượt `i`, `a[i-1] <= key`; vòng `while` không dịch lần nào. Có `n-1` lượt, mỗi lượt làm một số thao tác hằng số. Do đó số phép so sánh khóa là `n-1` với `n>=1`, thời gian tuyến tính.

Đặc tính này gọi là **thích nghi với dữ liệu gần có thứ tự** (*adaptive*): càng ít phần tử nằm sai thứ tự tương đối, thuật toán thường càng ít dịch.

### 4.2. Vì sao mảng giảm dần có thời gian bậc hai?

Nếu mọi phần tử đều phân biệt và dãy giảm nghiêm ngặt, ở lượt `i` phần tử mới nhỏ hơn tất cả `i` phần tử đứng trước. Vòng `while` dịch đúng `i` phần tử.

Tổng số lần dịch:

`1 + 2 + ... + (n-1) = n(n-1)/2 = Θ(n²)`.

Các phép so sánh cũng có cùng bậc. Thêm việc đọc/ghi phần tử không làm thay đổi kết luận.

### 4.3. Liên hệ chặt với số nghịch thế (*inversions*)

Một **nghịch thế** là một cặp vị trí `(p,q)` trong mảng **ban đầu** thỏa `p < q` nhưng `a[p] > a[q]` khi cần sắp xếp không giảm.

Gọi `I` là số nghịch thế của mảng. Trong insertion sort dạng **dịch phần tử** ở phần 2, mỗi lần dịch phần tử `a[j] > key` ứng với đúng một phần tử đứng trước `key` nhưng lớn hơn nó. Vì vậy:

- **Tổng số lần dịch phần tử lớn hơn `key` chính xác bằng `I`.**
- Mỗi lượt còn có chi phí hằng số và nhiều nhất một so sánh khóa thất bại khi chèn.

Do đó có thể mô tả chi phí thao tác là `O(n + I)` (với trường hợp `n=0` được hiểu là hằng số). Điều này giải thích rõ vì sao insertion sort tốt khi dữ liệu gần đã sắp.

Ví dụ `a=[5,2,4,6,1,3]`:

```text
Lượt chèn key=2: dịch 1 phần tử
Lượt chèn key=4: dịch 1 phần tử
Lượt chèn key=6: dịch 0 phần tử
Lượt chèn key=1: dịch 4 phần tử
Lượt chèn key=3: dịch 3 phần tử
Tổng: 1+1+0+4+3 = 9 lần dịch.
```

Số nghịch thế của mảng ban đầu cũng đúng bằng `9`. Với một hoán vị ngẫu nhiên đều của `n` giá trị **phân biệt**, mỗi cặp vị trí có xác suất `1/2` là nghịch thế; có `n(n-1)/2` cặp nên số nghịch thế kỳ vọng là `n(n-1)/4`.

**Bộ nhớ phụ:** thuật toán chuẩn chỉ cần `key`, `i`, `j` và vài biến — **`O(1)` bộ nhớ phụ**. Dữ liệu được sắp xếp **tại chỗ** (*in-place*) và không cần ngăn xếp đệ quy. Nó không phải thuật toán thời gian `O(n log n)` trong trường hợp xấu.

### 4.4. So sánh số phép so sánh và số lần di chuyển

Một thuật toán có thể giảm **số so sánh** nhưng vẫn phải **dịch nhiều phần tử**. Với insertion sort chuẩn, tìm vị trí bằng cách lùi tuần tự vừa so sánh vừa dịch. Nếu thay tìm kiếm tuyến tính bằng tìm kiếm nhị phân, số so sánh có thể hạ xuống `O(n log n)`, nhưng mảng vẫn phải dịch `O(n²)` phần tử trong trường hợp xấu. Vì vậy không được suy ra rằng “binary insertion sort có thời gian `O(n log n)`” khi vẫn dùng mảng và dịch phần tử.

## 5. Java 17: ổn định với các bản ghi có khóa trùng

Để kiểm tra ổn định, cần bản ghi gồm **khóa so sánh** và **ID phân biệt**. Ta có thể viết insertion sort tổng quát, dùng `Comparator` thay vì so sánh số nguyên trực tiếp.

Lưu thành **StableInsertionSort.java**:

```java
import java.util.Comparator;
import java.util.Objects;

public class StableInsertionSort {
    record Entry(int score, String id) {}

    static <T> void sort(T[] a, Comparator<? super T> comparator) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(comparator, "comparator");

        for (int i = 1; i < a.length; i++) {
            T key = a[i];
            int j = i - 1;

            // compare > 0: chỉ dịch phần tử có khóa lớn hơn.
            while (j >= 0 && comparator.compare(a[j], key) > 0) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = key;
        }
    }

    public static void main(String[] args) {
        Entry[] entries = {
            new Entry(3, "A"),
            new Entry(1, "B"),
            new Entry(3, "C"),
            new Entry(2, "D")
        };

        sort(entries, Comparator.comparingInt(Entry::score));
        for (Entry entry : entries) {
            System.out.println(entry.score() + ":" + entry.id());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StableInsertionSort.java
java StableInsertionSort
```

Stdout:

```text
1:B
2:D
3:A
3:C
```

Hai phần tử có `score=3` xuất hiện theo thứ tự **A rồi C**, giống thứ tự ban đầu. Để chương trình luôn đúng, comparator phải biểu diễn một thứ tự phù hợp (nhất quán, bắc cầu); ví dụ `Comparator.comparingInt` so sánh an toàn trên toàn miền `int` mà không viết phép trừ dễ tràn như `x.score()-y.score()`.

Bản tổng quát nhận mảng đối tượng có phần tử không `null` theo hợp đồng comparator ở đây. Nếu muốn hỗ trợ `null`, phải chọn comparator có quy tắc cụ thể, chẳng hạn `Comparator.nullsFirst(...)`, rồi bảo đảm mọi phần tử đều được xử lý theo quy tắc ấy.

### 5.1. Muốn sắp xếp giảm dần?

Đối với mảng số nguyên, ở vòng `while` thay `a[j] > key` thành `a[j] < key` để dịch các giá trị **nhỏ hơn** sang phải; kết quả sắp xếp **không tăng**. Giữ điều kiện **nghiêm ngặt** để không đảo thứ tự các khóa bằng nhau.

Trong phiên bản `Comparator`, đơn giản truyền comparator đảo ngược, chẳng hạn:

```java
Comparator<Entry> descending =
    Comparator.comparingInt(Entry::score).reversed();
```

Đây là **đoạn minh họa** trong cùng lớp đã khai báo `Entry`, không phải chương trình độc lập. `sort` vẫn sử dụng điều kiện `comparator.compare(a[j],key) > 0` nên đúng cả với comparator giảm dần.

## 6. Biến thể: binary insertion sort

Vì prefix đã có thứ tự, có thể dùng **tìm kiếm nhị phân** để xác định vị trí chèn thay vì so sánh lùi từng phần tử.

Để giữ tính ổn định, khi khóa bằng nhau phải chèn **sau** những phần tử bằng khóa đã nằm trong prefix. Ta tìm **upper bound**: chỉ số đầu tiên trong prefix có phần tử **lớn hơn** `key`; nếu không có thì vị trí chèn là `i`.

Sau đó dịch một khối `a[pos..i)` sang phải một vị trí (có thể dùng `System.arraycopy`) rồi đặt `key` vào `a[pos]`.

### 6.1. Java 17: upper bound và dịch khối

Lưu thành **BinaryInsertionSortDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class BinaryInsertionSortDemo {
    // Prefix [0, hi) đã sắp xếp không giảm.
    // Tìm vị trí đầu tiên có giá trị > key.
    static int upperBound(int[] a, int hi, int key) {
        int lo = 0;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] <= key) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    static void sort(int[] a) {
        Objects.requireNonNull(a, "a");

        for (int i = 1; i < a.length; i++) {
            int key = a[i];
            int pos = upperBound(a, i, key);

            if (pos < i) {
                System.arraycopy(a, pos, a, pos + 1, i - pos);
                a[pos] = key;
            }
        }
    }

    public static void main(String[] args) {
        int[] a = {5, 2, 4, 6, 1, 3};
        sort(a);
        System.out.println(Arrays.toString(a));

        int[] b = {3, 1, 3, 2, 3};
        sort(b);
        System.out.println(Arrays.toString(b));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BinaryInsertionSortDemo.java
java BinaryInsertionSortDemo
```

Stdout:

```text
[1, 2, 3, 4, 5, 6]
[1, 2, 3, 3, 3]
```

**Tại sao `System.arraycopy` ở đây an toàn?** Java xử lý các vùng chồng lấp trong cùng mảng theo cách tương đương với việc sao chép qua vùng tạm, nên dịch đoạn một ô sang phải giữ đúng thứ tự phần tử. Lời gọi chỉ diễn ra khi `pos<i`; đích đến kết thúc ở `i`, vẫn thuộc mảng.

**Độ phức tạp:**

- Mỗi lượt tìm kiếm vị trí dùng `O(log(i+1))` phép so sánh, tổng `O(n log n)` phép so sánh.
- Số phần tử phải dịch có thể vẫn là `1+2+...+(n-1)=Θ(n²)`.
- Thời gian tổng thể **xấu nhất `O(n²)`**, bộ nhớ phụ `O(1)` ngoài chi phí nội bộ hằng/tối ưu của thao tác sao chép.
- Trên dãy đã sắp xếp, không có dịch chuyển vì `pos=i`; tuy nhiên tìm kiếm nhị phân vẫn thực hiện khoảng `O(n log n)` phép so sánh ở toàn bộ lượt, khác insertion sort tuyến tính vốn chỉ `O(n)` khi đầu vào đã có thứ tự.

**Cái được cải thiện** là số phép **so sánh khóa**, đặc biệt có lợi nếu comparator rất đắt và chi phí dịch vùng nhớ tương đối rẻ. Nó không làm biến mất chi phí di chuyển phần tử.

**Phân biệt upper bound với lower bound:** nếu tìm vị trí đầu tiên `>= key` (*lower bound*) rồi chèn ở đó, phần tử mới có thể đứng **trước** các phần tử cùng khóa đã có, làm mất tính ổn định. Upper bound (`> key`) giữ phần tử cũ cùng khóa ở trước.

## 7. Biến thể dùng đổi chỗ liền kề

Một dạng insertion sort khác đưa phần tử mới về đúng vị trí bằng các phép **swap với hàng xóm bên trái**:

```java
// Đây là một phương thức minh họa, đặt trong lớp Java bất kỳ.
static void insertionSortBySwaps(int[] a) {
    for (int i = 1; i < a.length; i++) {
        for (int j = i; j > 0 && a[j] < a[j - 1]; j--) {
            int temp = a[j];
            a[j] = a[j - 1];
            a[j - 1] = temp;
        }
    }
}
```

Với thứ tự tăng, mỗi swap liền kề giữa hai giá trị đang ngược thứ tự làm số nghịch thế giảm đúng một. Vì thuật toán chỉ swap khi `a[j] < a[j-1]`, nó thực hiện đúng `I` phép swap và **vẫn ổn định**.

Tuy nhiên, một swap cần nhiều phép gán hơn việc dịch một phần tử. Vì vậy, khi dùng mảng, biến thể **lưu `key` rồi dịch khối** ở phần 2 thường có chi phí ghi thấp hơn. Biến thể swap lại dễ diễn giải trong những bài toán yêu cầu đếm số đổi chỗ liền kề ít nhất: số swap tối thiểu để sắp xếp các giá trị phân biệt bằng các đổi chỗ kề nhau chính là số nghịch thế.

**Không nhầm với bubble sort:** cả hai có thể dùng đổi chỗ các phần tử kề nhau, nhưng cơ chế vòng lặp khác. Insertion sort chọn từng phần tử tiếp theo đưa vào prefix đã có thứ tự; bubble sort liên tục quét và đẩy phần tử theo một chiều qua các lần quét.

## 8. Khi nào nên chọn insertion sort?

Insertion sort thường phù hợp khi:

- **Mảng nhỏ:** vòng lặp đơn giản, ít chi phí thiết lập, không cần cấp phát mảng phụ.
- **Dữ liệu gần có thứ tự:** số nghịch thế nhỏ nên số dịch nhỏ.
- **Muốn kết quả ổn định:** với điều kiện chỉ dịch phần tử lớn hơn (hoặc dùng comparator `> 0`).
- **Có luồng phần tử đến lần lượt, quy mô nhỏ:** có thể chèn từng phần tử mới vào cấu trúc đang giữ thứ tự. Với mảng, mỗi lần chèn vẫn có thể mất `O(n)` do dịch phần tử.
- **Thuật toán lai (*hybrid*):** nhiều cách sắp xếp chia để trị dùng biến thể của insertion sort cho các đoạn nhỏ vì chi phí đơn giản và tính hiệu quả thực tế trên kích thước nhỏ.

Những tình huống thường **không nên** dùng insertion sort thuần:

- Cần sắp xếp mảng lớn chưa có thứ tự; thời gian xấu nhất `Θ(n²)` dễ vượt giới hạn.
- Cần nhiều lần chèn/xóa vào tập dữ liệu lớn đã sắp thứ tự: mảng có chi phí dịch `O(n)` mỗi lần; cân nhắc cấu trúc cây cân bằng hoặc cấu trúc lưu trữ khác theo yêu cầu truy vấn.
- Bài toán yêu cầu sắp nhiều triệu bản ghi với giới hạn thời gian chặt; thông thường nên chọn thuật toán có độ phức tạp `O(n log n)` (merge sort/heapsort/quicksort với các bảo đảm phù hợp) hoặc thư viện chuẩn.

### 8.1. So sánh với vài họ sắp xếp khác

| Thuật toán | Tốt nhất | Xấu nhất | Bộ nhớ phụ điển hình | Ổn định? | Gợi ý nhận diện |
|---|---|---|---|---|---|
| **Insertion sort (dịch)** | `Θ(n)` | `Θ(n²)` | `O(1)` | Có, với `>` | Mảng nhỏ, gần có thứ tự |
| **Selection sort** | `Θ(n²)` | `Θ(n²)` | `O(1)` | Thường không ổn định với swap chuẩn | Muốn hạn chế số lần swap |
| **Bubble sort có dừng sớm** | `Θ(n)` | `Θ(n²)` | `O(1)` | Có với swap nghiêm ngặt | Minh họa đổi chỗ kề nhau |
| **Merge sort trên mảng** | `Θ(n log n)` | `Θ(n log n)` | Thường `O(n)` | Có nếu merge ưu tiên phía trái khi hòa | Cần thời gian bảo đảm |
| **Quicksort thông dụng** | Trung bình `Θ(n log n)` | `Θ(n²)` | Phụ thuộc đệ quy/phân hoạch | Thường không | Chia để trị tại chỗ, phụ thuộc pivot |

Bảng mô tả phiên bản điển hình. Các biến thể đặc biệt có thể khác, nên khi so sánh phải ghi rõ cài đặt và yêu cầu của bài.

### 8.2. “Online” nghĩa là gì?

Trong một cách dùng phổ biến, insertion sort là thuật toán **online**: khi phần tử tiếp theo xuất hiện, ta có thể đưa nó vào dãy đang sắp mà không cần biết các phần tử tương lai. Sau mỗi lượt, đoạn đã nhận có thứ tự.

Nhưng **online không đồng nghĩa chèn `O(1)`**. Với mảng liên tiếp, tìm vị trí và dịch các phần tử có thể tốn tuyến tính theo số phần tử đã nhận. Nếu cần lượng dữ liệu động lớn, cấu trúc cây tìm kiếm cân bằng hoặc cấu trúc chuyên dụng có thể phù hợp hơn.

## 9. Các lỗi triển khai thường gặp

### 9.1. Quên lưu `key` trước khi dịch

Nếu trực tiếp ghi `a[j+1]=a[j]` mà không giữ giá trị gốc tại `a[i]`, phần tử cần chèn có thể bị ghi đè. Luôn lưu `key=a[i]` trước vòng `while`.

### 9.2. Đặt phần tử vào sai vị trí

Khi vòng `while` dừng, `j` chỉ vào phần tử cuối `<=key` hoặc bằng `-1`. Ô đúng để ghi `key` là **`j+1`**, không phải `j`. Ghi `a[j]` khi `j=-1` sẽ gây ngoại lệ.

### 9.3. Đảo thứ tự điều kiện của `&&`

Điều kiện an toàn là:

```java
while (j >= 0 && a[j] > key) {
    // ...
}
```

Nếu viết `a[j] > key && j >= 0`, Java có thể truy cập `a[-1]` trước khi kiểm tra biên. `&&` trong Java đánh giá từ trái sang phải và ngắn mạch.

### 9.4. Vô tình phá ổn định khi gặp phần tử bằng nhau

Dùng `>=` để dịch những phần tử bằng khóa khiến bản ghi đến sau có thể chèn trước bản ghi cũ. Nếu bài yêu cầu ổn định, chỉ dịch khi **lớn hơn hẳn**.

### 9.5. Comparator sai vì tràn số

Với các số nguyên `int` có thể rất lớn hoặc âm, viết `(x, y) -> x - y` có thể tràn số làm thứ tự sai. Dùng `Integer.compare(x,y)` hoặc `Comparator.comparingInt(...)`.

### 9.6. Nghĩ rằng binary insertion sort luôn `O(n log n)`

Tìm vị trí bằng binary search giảm **so sánh**. Các phần tử trong mảng vẫn có thể phải dịch `Θ(n²)` lần, nên thời gian xấu nhất vẫn là bậc hai.

### 9.7. Nhầm độ phức tạp bộ nhớ với thời gian

Dạng tại chỗ dùng `O(1)` bộ nhớ phụ, nhưng không vì vậy mà nhanh trên mảng ngược thứ tự lớn. Bộ nhớ thấp và thời gian thấp là hai tiêu chí độc lập.

### 9.8. Bỏ quên mảng rỗng và một phần tử

Vòng ngoài phải bắt đầu `i=1` và dừng khi `i<n`. Nhờ đó mảng rỗng hoặc một phần tử không bị truy cập ngoài biên.

### 9.9. Sao chép đoạn chưa xử lý quá xa

Ở lượt `i`, chỉ được dịch các phần tử trong **prefix** `0..i-1` sang tối đa vị trí `i`. Không cần dịch phần tử ở `i+1` trở đi, vì chúng chưa được xử lý và phải giữ nguyên cho các lượt kế tiếp.

### 9.10. Đoạn đã sắp xếp không theo cùng comparator

Nếu vòng `while` so sánh tăng nhưng phần tử mới/chương trình khác lại dùng comparator giảm hoặc không nhất quán, bất biến prefix có thứ tự sẽ mất hiệu lực. Cần một quy tắc thứ tự xuyên suốt.

## 10. Kiểm thử có chủ đích và kiểm chứng

| Input | Output tăng không giảm | Mục đích |
|---|---|---|
| `[]` | `[]` | Biên mảng rỗng |
| `[7]` | `[7]` | Một phần tử |
| `[1,2,3]` | `[1,2,3]` | Trường hợp tốt nhất |
| `[3,2,1]` | `[1,2,3]` | Trường hợp xấu nhất với khóa phân biệt |
| `[5,5,5]` | `[5,5,5]` | Tất cả bằng nhau |
| `[0,-2,7,-2]` | `[-2,-2,0,7]` | Số âm, số trùng |
| `[2,1,2,1]` | `[1,1,2,2]` | Trùng xen kẽ |
| `[Integer.MAX_VALUE,Integer.MIN_VALUE]` | `[Integer.MIN_VALUE,Integer.MAX_VALUE]` | Biên `int`, so sánh trực tiếp an toàn |

Có thể tạo một **oracle kiểm thử** bằng `Arrays.sort` trên bản sao dữ liệu rồi so sánh với kết quả insertion sort; đây là cách phát hiện lỗi thực thi ở nhiều mảng nhỏ, không thay thế chứng minh bằng bất biến.

Đối với bản ghi có cùng khóa, cần so sánh cả thứ tự **ID** sau sắp xếp để kiểm tra ổn định; chỉ so sánh giá trị khóa không phát hiện được lỗi `>=`.

Các điều kiện cần kiểm chứng độc lập:

1. **Có thứ tự:** với mọi `i>0`, `a[i-1] <= a[i]`.
2. **Bảo toàn đa tập:** mỗi giá trị xuất hiện đúng số lần trước và sau.
3. **Ổn định khi yêu cầu:** các ID cùng khóa xuất hiện theo thứ tự gốc.
4. **Dừng và an toàn biên:** thuật toán xử lý rỗng, một phần tử, âm, trùng mà không truy cập sai.
5. **Chi phí hợp lý:** trên dãy gần có thứ tự, đo số dịch sẽ nhỏ; trên dãy giảm dần, số dịch tăng xấp xỉ bình phương.

## 11. Bài tập vận dụng có đáp án

**Bài 1 — Lần theo insertion sort.** Sắp tăng `a=[4,3,1,2]`. Ghi lại mảng sau mỗi lượt `i`.

**Đáp án:**

```text
i=1, key=3: [3,4,1,2]
i=2, key=1: [1,3,4,2]
i=3, key=2: [1,2,3,4]
```

Tổng số dịch là `1+2+2=5`, đúng bằng số nghịch thế của đầu vào.

**Bài 2 — Trường hợp tốt nhất.** Với `a=[-5,-1,0,2,2,9]`, có bao nhiêu phần tử cần dịch khi dùng bản chuẩn?

**Đáp án:** không có phần tử nào phải dịch; mọi `key` đều lớn hơn hoặc bằng phần tử cuối prefix. Có `n-1=5` phép so sánh khóa trong vòng `while`, thời gian tuyến tính.

**Bài 3 — Trường hợp xấu nhất.** Với `n=6` phần tử phân biệt giảm nghiêm ngặt, có bao nhiêu lần dịch phần tử?

**Đáp án:** `1+2+3+4+5=15` lần. Tổng quát: `n(n-1)/2`.

**Bài 4 — Giữ ổn định.** Cho các bản ghi `(2,A), (1,B), (2,C), (1,D)`. Sau sắp xếp ổn định theo khóa, thứ tự thế nào?

**Đáp án:** `(1,B), (1,D), (2,A), (2,C)`. `B` vẫn trước `D` và `A` vẫn trước `C` trong từng nhóm khóa.

**Bài 5 — Tìm vị trí bằng binary search.** Prefix đã sắp là `[1,3,3,5]`, `key=3`. Muốn ổn định, chèn `key` ở vị trí nào (0-based)?

**Đáp án:** vị trí `3` (sau hai số `3` hiện có), tức `upperBound=3`. Chèn ở vị trí `1` là lower bound và có thể đảo thứ tự các bản ghi cùng khóa.

**Bài 6 — Chọn thuật toán.** Một mảng hàng triệu phần tử gần như đảo ngược và cần sắp xếp hoàn toàn. Có nên dùng insertion sort thuần không?

**Đáp án:** thường không. Số nghịch thế rất lớn, insertion sort có thời gian bậc hai. Nên xem thuật toán có chặn tốt hơn như merge sort hoặc thư viện sắp xếp phù hợp.

## 12. Checklist áp dụng cho đề mới

Khi nhận một bài toán sắp xếp, trả lời tuần tự:

1. **Sắp theo khóa nào và theo chiều nào?** Tăng, giảm, nhiều khóa; comparator có nhất quán không?
2. **Có bắt buộc ổn định không?** Nếu có, chỉ dịch phần tử “đứng sau” nghiêm ngặt theo comparator.
3. **Đầu vào lớn đến đâu?** Với `n` lớn, trường hợp xấu `Θ(n²)` thường không phù hợp.
4. **Dữ liệu gần có thứ tự không?** Ít nghịch thế giúp insertion sort thường hiệu quả.
5. **Có được sửa trực tiếp đầu vào không?** Insertion sort chuẩn thay đổi mảng tại chỗ, dùng `O(1)` bộ nhớ phụ.
6. **Số lần so sánh hay di chuyển mới là nút thắt?** Binary insertion giảm số so sánh nhưng không giảm tổng số phần tử có thể phải dịch.
7. **Có yêu cầu thời gian xấu nhất?** Nếu cần bảo đảm `O(n log n)`, chọn thuật toán khác hoặc chiến lược lai có phân tích rõ ràng.
8. **Có các trường hợp biên?** Rỗng, một phần tử, trùng, âm, mảng đã sắp, mảng giảm, dữ liệu rất lớn.
9. **Có thể giải thích vì sao đúng?** Bất biến prefix có thứ tự và bảo toàn đa tập, bước chèn giữ bất biến, vòng lặp luôn dừng.

**Ghi nhớ:** insertion sort duy trì **một prefix đã có thứ tự**, rồi chèn từng phần tử mới vào đúng vị trí. Bản dịch phần tử chuẩn **ổn định, tại chỗ `O(1)` bộ nhớ phụ, chạy `Θ(n)` trên dãy đã sắp**, nhưng **`Θ(n²)` ở trung bình và xấu nhất**. Số lần dịch chính là số nghịch thế của đầu vào, nên mức độ gần có thứ tự quyết định rất mạnh hiệu năng thực tế.
