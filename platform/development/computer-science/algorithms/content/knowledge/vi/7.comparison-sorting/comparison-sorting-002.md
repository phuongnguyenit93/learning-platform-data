# Tính ổn định, tại chỗ và khả năng thích nghi

Khi chọn thuật toán **sắp xếp so sánh (comparison sorting)**, độ phức tạp thời gian O(n log n) hay O(n²) chưa nói hết đặc điểm của thuật toán. Ba tính chất có ảnh hưởng trực tiếp đến dữ liệu và chi phí thực tế là:

- **Tính ổn định (stability):** các phần tử **có khóa so sánh bằng nhau** có giữ nguyên thứ tự tương đối như lúc đầu không?
- **Tính tại chỗ (in-place):** thuật toán cần bao nhiêu **bộ nhớ phụ** ngoài vùng dữ liệu phải sắp xếp?
- **Khả năng thích nghi (adaptivity):** thuật toán có tận dụng mức độ **đã có thứ tự** của đầu vào để giảm công việc không?

Đây là **ba thuộc tính khác nhau**. Một thuật toán có thể vừa ổn định vừa tại chỗ và thích nghi; thuật toán khác có thể tại chỗ nhưng không ổn định; một thuật toán khác ổn định và thích nghi nhưng dùng thêm bộ nhớ. Không thể suy ra hai tính chất còn lại chỉ từ một tính chất.

## 1. Vì sao tính ổn định quan trọng?

Giả sử dữ liệu là các bản ghi `(điểm, mã)` và ta muốn sắp xếp theo **điểm tăng dần**, không dùng mã để phá hòa:

```text
Đầu vào:       (80,A), (90,B), (80,C), (70,D)
Khóa so sánh:  điểm
Ổn định:       (70,D), (80,A), (80,C), (90,B)
```

Hai bản ghi `(80,A)` và `(80,C)` có **cùng khóa 80**; `A` xuất hiện trước `C` trong đầu vào, nên sắp xếp ổn định phải giữ `A` trước `C` ở kết quả. Nếu thuật toán trả `(70,D), (80,C), (80,A), (90,B)`, các khóa đã tăng dần nhưng kết quả **không ổn định**.

**Định nghĩa chính xác:** với hai vị trí đầu vào `i < j` có `key(A[i]) = key(A[j])`, thuật toán ổn định phải giữ phần tử xuất phát từ `i` đứng trước phần tử xuất phát từ `j` trong đầu ra. Tính ổn định nói về thứ tự **giữa các phần tử bằng nhau theo comparator**, chứ không nói phần tử ở nguyên chỉ số cũ hay nhóm dữ liệu đã được sắp xếp hoàn toàn.

### Sắp xếp nhiều tiêu chí bằng nhiều lượt

Ví dụ cần sắp xếp nhân viên theo **phòng ban tăng dần**, và trong mỗi phòng ban theo **thời điểm đăng ký tăng dần**. Có thể:

1. Sắp xếp **ổn định** theo thời điểm đăng ký (tiêu chí phụ).
2. Sắp xếp **ổn định** theo phòng ban (tiêu chí chính).

Lượt thứ hai đặt các nhân viên cùng phòng ban vào một nhóm, nhưng nhờ tính ổn định, thứ tự đăng ký đã có ở lượt thứ nhất vẫn giữ trong nhóm. **Nếu lượt sắp xếp cuối không ổn định**, quy tắc này có thể bị phá.

Cách khác là dùng một comparator so sánh trực tiếp cặp `(phòng ban, thời điểm)`. Khi đã dùng comparator tổng hợp có quy tắc phá hòa, khái niệm “bằng nhau” để xét stability sẽ là bằng nhau theo **toàn bộ comparator**, không chỉ theo phòng ban.

### Ví dụ một thuật toán có thể làm mất ổn định

Selection sort cơ bản tìm phần tử nhỏ nhất trong đoạn chưa sắp xếp rồi **hoán đổi trực tiếp** với vị trí đầu đoạn. Xét ba bản ghi:

```text
Đầu vào:      (2,A), (2,B), (1,C)
Lượt đầu:     đổi (2,A) với (1,C)
Sau đổi:      (1,C), (2,B), (2,A)
```

Mảng kết quả có khóa tăng dần nhưng `B` đứng trước `A`, dù ban đầu `A` đứng trước `B`. Do đó **selection sort dùng swap như trên không ổn định**. Đây là phản ví dụ cụ thể; không cần khẳng định mọi thuật toán “chọn phần tử nhỏ nhất” đều bất ổn định, vì có thể thiết kế phiên bản dịch chuyển ổn định với chi phí khác.

## 2. Sắp xếp tại chỗ (in-place) là gì?

Trong phân tích thuật toán, thuật ngữ **in-place** thường dùng khi lượng **bộ nhớ phụ** chỉ là **O(1)** so với kích thước `n` của mảng đầu vào. Mảng đầu vào đã được cung cấp không tính là bộ nhớ phụ; một vài biến chỉ số, biến tạm để đổi chỗ cũng chỉ chiếm lượng không đổi.

Ví dụ, đổi chỗ hai vị trí của mảng:

```text
temp <- A[i]
A[i] <- A[j]
A[j] <- temp
```

Chỉ cần một biến `temp`, nên bước đổi chỗ là tại chỗ. Nếu thuật toán dành thêm một mảng `buffer` dài `n` để lưu kết quả, bộ nhớ phụ là **O(n)** và không được gọi là O(1) tại chỗ theo nghĩa chặt chẽ.

**Ba điều cần phân biệt:**

- **Sửa trực tiếp mảng** không đủ để chứng minh in-place: thuật toán vẫn có thể vừa sửa mảng vừa cấp một vùng phụ dài `n`.
- **Sử dụng đệ quy** có thể tiêu tốn bộ nhớ ngăn xếp lời gọi. Một phép phân hoạch quicksort có thể dùng O(1) biến phụ, nhưng quicksort đệ quy thông thường còn tốn bộ nhớ stack: thường O(log n) khi chia cân đối, có thể O(n) trong trường hợp xấu. Không nên tuyên bố toàn bộ phiên bản đệ quy ấy dùng O(1) bộ nhớ.
- **Tạo bản sao đầu vào để giữ dữ liệu gốc** là chi phí của quy trình tổng thể. Trong ví dụ Java ở phần sau, các lệnh `clone()` chỉ giúp chạy ba thuật toán độc lập trên cùng dữ liệu ban đầu; chúng **không nằm bên trong** bản thân `insertionSort` hoặc `selectionSort`.

### Ví dụ so sánh merge sort và heap sort

**Merge sort thông thường trên mảng:** chia dãy, sắp hai nửa rồi gộp. Khi gộp, cách cài đặt đơn giản và phổ biến dùng bộ đệm phụ có kích thước O(n). Merge sort có thể ổn định nếu khi hai khóa bằng nhau nó lấy phần tử từ **nửa trái trước**, nhưng phiên bản dùng bộ đệm ấy không phải sắp xếp tại chỗ O(1).

**Heap sort:** xây dựng heap ngay trên mảng rồi nhiều lần chuyển phần tử lớn nhất về cuối, dùng O(1) bộ nhớ phụ trong cách cài đặt heap sort mảng không đệ quy. Heap sort thông thường **không ổn định** vì các phép hoán đổi không bảo toàn thứ tự ban đầu của các khóa bằng nhau.

Không nên kết luận “ổn định thì không thể tại chỗ”: **insertion sort** là ví dụ cơ bản vừa ổn định vừa tại chỗ. Cũng có các biến thể sắp xếp ổn định tại chỗ phức tạp hơn.

## 3. Khả năng thích nghi (adaptive) với dữ liệu đã có thứ tự

Một thuật toán **thích nghi** nếu mức độ có thứ tự sẵn của đầu vào làm giảm lượng công việc so với trường hợp dữ liệu lộn xộn. Việc “có vẻ chạy nhanh trên máy này” không đủ để định nghĩa khả năng thích nghi; nên mô tả được công việc giảm dựa trên một thuộc tính của đầu vào, chẳng hạn:

- **Số nghịch thế (inversions)**: cặp chỉ số `i < j` mà `A[i] > A[j]` theo khóa. Mảng tăng dần có 0 nghịch thế; mảng gồm `n` khóa phân biệt giảm dần có `n(n-1)/2` nghịch thế.
- **Các đoạn chạy đã có thứ tự (runs)**: các đoạn liên tiếp vốn đã tăng hoặc giảm. Thuật toán tận dụng các runs có thể làm ít thao tác hơn khi dữ liệu gần được sắp xếp.
- **Khoảng cách di chuyển** của phần tử so với vị trí đúng của nó.

Không có nghĩa **mọi thuật toán sắp xếp** đều tự động thích nghi. Một selection sort cơ bản vẫn so sánh gần như cùng số cặp, bất kể đầu vào đã tăng dần hay đảo ngược. Trái lại, insertion sort thường làm ít dịch chuyển khi dữ liệu gần có thứ tự.

### Insertion sort và số nghịch thế

Với insertion sort dùng dịch chuyển, mỗi lần chèn `A[i]` vào đoạn đầu đã sắp, các phần tử **lớn hơn** khóa đang chèn bị dịch sang phải. Mỗi lần dịch một phần tử lớn hơn qua phần tử đang chèn tương ứng với việc xử lý một nghịch thế. Vì thế có thể phân tích thời gian của insertion sort là **O(n + I)** với `I` là số nghịch thế:

- Dãy đã tăng dần: `I=0`, thời gian **O(n)**.
- Dãy gần tăng dần: `I` nhỏ, thời gian gần tuyến tính.
- Dãy giảm dần với khóa phân biệt: `I=n(n-1)/2`, thời gian **O(n²)**.

Đối với insertion sort dạng thông thường, best case là O(n), worst case là O(n²). Điều này không mâu thuẫn với cận dưới **Ω(n log n) trong trường hợp xấu nhất** cho thuật toán sắp xếp so sánh tổng quát: cận dưới nói về **mọi đầu vào trong trường hợp xấu nhất**, không cấm một thuật toán chạy nhanh trên đầu vào đặc biệt.

### Bubble sort có tối ưu thoát sớm

Một bubble sort chỉ đổi chỗ khi khóa trái **lớn hơn** khóa phải có thể ổn định. Nếu thêm biến `swapped` và dừng ngay sau lượt quét không có đổi chỗ, nó chạy O(n) trên mảng đã sắp xếp. Nếu **không có kiểm tra thoát sớm**, phiên bản lặp cố định có thể vẫn làm O(n²) phép so sánh ngay cả trên mảng có thứ tự.

Điều này cho thấy **khả năng thích nghi phụ thuộc phiên bản cụ thể**, không chỉ phụ thuộc tên thuật toán.

## 4. Insertion sort: ổn định, tại chỗ và thích nghi

Insertion sort duy trì đoạn đầu mảng đã được sắp xếp, rồi lần lượt lấy phần tử tiếp theo và **chèn** vào vị trí thích hợp trong đoạn ấy.

Giả mã cho mảng bản ghi có khóa `KEY(x)`:

```text
ALGORITHM STABLE_INSERTION_SORT(A)
    n <- LENGTH(A)

    FOR i FROM 1 TO n - 1 DO
        chosen <- A[i]
        j <- i - 1

        WHILE j >= 0 AND KEY(A[j]) > KEY(chosen) DO
            A[j + 1] <- A[j]
            j <- j - 1
        END WHILE

        A[j + 1] <- chosen
    END FOR
END ALGORITHM
```

Điều kiện trong vòng `WHILE` là **`>`**, không phải `>=`. Nhờ vậy, khi gặp bản ghi có khóa **bằng** khóa của `chosen`, vòng lặp dừng và chèn `chosen` **sau** những bản ghi bằng khóa đã đứng trước nó. Đây chính là điểm quyết định tính ổn định.

**Bất biến:** ngay trước lượt `i`, đoạn `A[0..i-1]` đã được sắp xếp theo khóa và giữ nguyên thứ tự tương đối của các khóa bằng nhau từ đầu vào. Thao tác dịch những phần tử có khóa lớn hơn sang phải và chèn `chosen` giữ tính sắp xếp lẫn ổn định. Khi `i=n`, toàn bộ mảng thỏa điều kiện.

Vòng ngoài chạy `n-1` lượt, vòng trong luôn giảm `j` cho đến khi dừng, nên thuật toán kết thúc. Mỗi lượt chỉ dùng biến `chosen` và `j`: **O(1) bộ nhớ phụ**. Có thể phân tích số lần dịch là đúng số nghịch thế liên quan đến các phần tử đang chèn, nên thời gian O(n+I), worst case O(n²).

**Biên:** mảng rỗng hoặc một phần tử không vào vòng ngoài, nên kết quả giữ nguyên. Những phần tử có khóa trùng nhau giữ thứ tự. Với dữ liệu tăng dần, vòng trong kiểm tra một lần rồi dừng ở mỗi lượt. Với dữ liệu giảm dần, gần như mọi phần tử mới phải được dịch về đầu.

## 5. Selection sort cơ bản: tại chỗ nhưng không ổn định và không thích nghi

Selection sort chọn phần tử nhỏ nhất ở đoạn chưa sắp và đổi chỗ trực tiếp với đầu đoạn:

```text
ALGORITHM SELECTION_SORT_BY_SWAP(A)
    n <- LENGTH(A)

    FOR i FROM 0 TO n - 2 DO
        minIndex <- i

        FOR j FROM i + 1 TO n - 1 DO
            IF KEY(A[j]) < KEY(A[minIndex]) THEN
                minIndex <- j
            END IF
        END FOR

        SWAP(A[i], A[minIndex])
    END FOR
END ALGORITHM
```

**Bất biến:** sau `i` lượt, `A[0..i-1]` chứa `i` khóa nhỏ nhất đã ở đúng vị trí theo thứ tự không giảm. Tuy nhiên, các lần **SWAP** có thể đẩy một bản ghi bằng khóa qua bản ghi khác bằng khóa như ví dụ `(2,A),(2,B),(1,C)`; vì vậy phiên bản này **không ổn định**.

Nó chỉ cần các biến chỉ số và biến tạm khi đổi chỗ, tức O(1) bộ nhớ phụ. Số so sánh khóa vẫn là `n(n-1)/2` trong bản cơ bản, **kể cả khi đầu vào đã sắp xếp**, nên không thích nghi theo mức độ có thứ tự của dữ liệu. Thời gian là Θ(n²), thường có ít lần hoán đổi hơn bubble sort nhưng điều đó không làm tổng số so sánh giảm.

Đặc biệt, **việc tránh swap khi `minIndex == i`** chỉ giảm thao tác ghi; không biến selection sort cơ bản thành thuật toán thích nghi về số lần so sánh.

## 6. Java 17+: so sánh ba thuật toán trên cùng dữ liệu

Chương trình dưới đây cho thấy **insertion sort ổn định**, **selection sort dùng swap không ổn định** và **`Arrays.sort` trên mảng đối tượng với comparator bảo đảm ổn định** theo hợp đồng API Java. Đồng thời đếm số lần so sánh khóa trong insertion sort trên các mảng số nguyên có mức độ có thứ tự khác nhau.

Tạo tệp **`SortPropertiesDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;

public class SortPropertiesDemo {
    record Item(int key, String tag) {}

    static void insertionSort(Item[] a) {
        for (int i = 1; i < a.length; i++) {
            Item chosen = a[i];
            int j = i - 1;

            while (j >= 0 && a[j].key() > chosen.key()) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = chosen;
        }
    }

    static void selectionSort(Item[] a) {
        for (int i = 0; i < a.length - 1; i++) {
            int minIndex = i;
            for (int j = i + 1; j < a.length; j++) {
                if (a[j].key() < a[minIndex].key()) {
                    minIndex = j;
                }
            }
            Item temp = a[i];
            a[i] = a[minIndex];
            a[minIndex] = temp;
        }
    }

    static long insertionComparisons(int[] a) {
        long comparisons = 0;
        for (int i = 1; i < a.length; i++) {
            int chosen = a[i];
            int j = i - 1;

            while (j >= 0) {
                comparisons++; // Chỉ đếm lần so sánh hai giá trị.
                if (a[j] <= chosen) {
                    break;
                }
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = chosen;
        }
        return comparisons;
    }

    static String show(Item[] a) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < a.length; i++) {
            if (i > 0) {
                out.append(", ");
            }
            out.append("(")
               .append(a[i].key())
               .append(",")
               .append(a[i].tag())
               .append(")");
        }
        return out.append("]").toString();
    }

    public static void main(String[] args) {
        Item[] original = {
            new Item(2, "A"),
            new Item(2, "B"),
            new Item(1, "C"),
            new Item(3, "D")
        };

        Item[] insertion = original.clone();
        Item[] selection = original.clone();
        Item[] library = original.clone();

        insertionSort(insertion);
        selectionSort(selection);
        Arrays.sort(library, Comparator.comparingInt(Item::key));

        System.out.println("insertion=" + show(insertion));
        System.out.println("selection=" + show(selection));
        System.out.println("library=" + show(library));

        int[] sorted = {1, 2, 3, 4, 5, 6};
        int[] almost = {1, 2, 3, 5, 4, 6};
        int[] reversed = {6, 5, 4, 3, 2, 1};

        System.out.println("sortedComparisons=" +
                insertionComparisons(sorted));
        System.out.println("almostComparisons=" +
                insertionComparisons(almost));
        System.out.println("reverseComparisons=" +
                insertionComparisons(reversed));
        System.out.println("almostSorted=" + Arrays.toString(almost));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SortPropertiesDemo.java
java SortPropertiesDemo
```

Kết quả chính xác:

```text
insertion=[(1,C), (2,A), (2,B), (3,D)]
selection=[(1,C), (2,B), (2,A), (3,D)]
library=[(1,C), (2,A), (2,B), (3,D)]
sortedComparisons=5
almostComparisons=6
reverseComparisons=15
almostSorted=[1, 2, 3, 4, 5, 6]
```

**Đọc kết quả:**

- Bản ghi `A` và `B` đều có `key=2`. Insertion sort và `Arrays.sort` giữ `A` trước `B`; selection sort đổi thành `B` trước `A` sau khi hoán đổi `C` về đầu.
- Các lệnh `clone()` chỉ sao chép mảng **để giữ dữ liệu ban đầu cho từng lần trình diễn**. Vì mỗi bản sao được tạo trước khi gọi thuật toán, việc so sánh kết quả không lẫn với tác động của thuật toán đã chạy trước. Khi phân tích riêng hàm `insertionSort`/`selectionSort`, hai hàm vẫn dùng O(1) bộ nhớ phụ.
- Bộ đếm `insertionComparisons` đếm **so sánh hai giá trị số nguyên**, không đếm phép kiểm tra chỉ số `j>=0`. Với dãy tăng dần dài 6 có 5 so sánh; đảo ngược có `1+2+3+4+5=15`; dãy gần sắp chỉ có một nghịch thế nên đếm 6.
- `StringBuilder` trong hàm `show` và `Arrays.toString` dùng bộ nhớ để **hiển thị** dữ liệu, không thuộc thuật toán sắp xếp đang được phân tích.
- Lời gọi `Arrays.sort(library, Comparator.comparingInt(Item::key))` chỉ so sánh trường `key`. Vì overload sắp xếp mảng **đối tượng** của Java có tính ổn định, hai phần tử bằng khóa giữ thứ tự. Không nên suy rộng bảo đảm này cho mọi cấu trúc/kiểu dữ liệu hoặc mọi thuật toán sắp xếp.

## 7. Bảng so sánh các thuật toán sắp xếp phổ biến

Các đặc tính trong bảng áp dụng cho **phiên bản tiêu chuẩn được nêu**, không phủ nhận sự tồn tại của các biến thể khác:

| Thuật toán / phiên bản | Ổn định? | Tại chỗ O(1) phụ? | Thích nghi? | Thời gian điển hình |
| --- | --- | --- | --- | --- |
| **Insertion sort** (dịch khi `>`) | Có | Có | Có, theo số nghịch thế | Best O(n), worst O(n²). |
| **Selection sort** (tìm min rồi swap) | Không | Có | Không trong bản cơ bản | Θ(n²) so sánh. |
| **Bubble sort** (đổi khi `>`, có dừng sớm) | Có | Có | Có ở trường hợp đã có thứ tự | Best O(n), worst O(n²). |
| **Heap sort** trên mảng | Không trong bản thông dụng | Có | Không trong bản thông dụng | O(n log n) worst-case. |
| **Merge sort** với bộ đệm gộp thông dụng | Có nếu lấy từ nửa trái khi bằng khóa | Không, thường O(n) phụ | Bản chuẩn không khai thác nhiều tính có thứ tự | O(n log n). |
| **Quicksort** phân hoạch và đệ quy thông dụng | Không | Phân hoạch O(1), nhưng còn stack đệ quy | Không mặc định | Trung bình O(n log n), worst O(n²). |
| **Sắp xếp khai thác runs** (ví dụ kiểu TimSort) | Có ở các triển khai ổn định | Thường dùng bộ nhớ phụ tăng theo kích thước | Có thể khai thác các runs | Phụ thuộc thuật toán và cấu trúc đầu vào. |

**Lưu ý về thuật ngữ in-place:** nhiều tài liệu gọi quicksort là “in-place” vì thao tác phân hoạch diễn ra trực tiếp trên mảng mà không cần mảng đệm O(n). Theo nghĩa **O(1) bộ nhớ phụ tính cả stack** của bài này, quicksort đệ quy thông thường không thỏa. Vì vậy luôn nói rõ **có tính stack đệ quy hay không** khi so sánh bộ nhớ.

**Lưu ý về tính thích nghi:** khi bản triển khai tận dụng các đoạn runs sẵn có, chi phí có thể giảm đáng kể trên dữ liệu gần được sắp xếp, nhưng không phải mọi merge sort hay mọi quicksort đều tự động thích nghi. Không được suy ra đặc điểm một phiên bản thư viện chỉ từ tên thuật toán.

## 8. Ba thuộc tính có liên hệ nhưng không thay thế nhau

- Một thuật toán **ổn định** không tự động **nhanh**, cũng không tự động dùng ít bộ nhớ. Insertion sort ổn định nhưng có thể O(n²); merge sort ổn định với bộ đệm thường O(n log n) nhưng tốn O(n) bộ nhớ phụ.
- Một thuật toán **tại chỗ** không tự động **ổn định**. Selection sort và heap sort phổ biến là những phản ví dụ.
- Một thuật toán **thích nghi** không nhất thiết **tại chỗ**. Các kỹ thuật dựa trên runs có thể dùng bộ đệm để gộp dữ liệu.
- Một thuật toán **không thích nghi** vẫn có thể phù hợp nhờ bảo đảm worst-case, ít bộ nhớ hoặc thao tác ghi ít. Ví dụ selection sort có O(n²) so sánh, nhưng trong bản chọn–đổi chỗ mỗi lượt chỉ cần tối đa một swap; điều này có thể hữu ích nếu số lần ghi đắt hơn so sánh và dữ liệu nhỏ.
- Thuộc tính còn phụ thuộc **bộ so sánh (comparator)**. Nếu comparator đưa một tiêu chí phụ vào phép so sánh, hai bản ghi tưởng như “bằng” theo một trường chưa chắc được coi là bằng theo comparator thực tế.

Trong lựa chọn thực tế, cần hỏi trước: dữ liệu có bản ghi trùng khóa và cần giữ thứ tự không; có được phép thay đổi đầu vào không; bộ nhớ phụ cho phép là bao nhiêu; dữ liệu gần sắp xếp hay hoàn toàn ngẫu nhiên; có yêu cầu worst-case không; và quy mô `n` thế nào.

## 9. Cách kiểm thử ba tính chất

### Kiểm thử tính ổn định

Không thể kiểm tra stability bằng mảng số nguyên trùng nhau thuần túy mà không đánh dấu danh tính từng phần tử, vì hai số 2 nhìn giống nhau. Hãy dùng bản ghi `(key, originalId)`; sau sắp xếp, kiểm tra:

1. Các khóa phải không giảm.
2. Trong mỗi nhóm có cùng khóa, `originalId` hoặc **vị trí xuất hiện ban đầu** phải tăng theo thứ tự ban đầu.

Ví dụ `[(2,A),(2,B),(1,C)]` đủ để phát hiện selection sort dùng swap không ổn định.

### Kiểm thử bộ nhớ phụ

Không suy ra in-place chỉ bằng việc mảng đầu vào bị sửa. Cần kiểm tra hoặc phân tích mã: có cấp mảng `n` phần tử không, có thêm cấu trúc như stack/queue hoặc collection cỡ `n` không, đệ quy sâu bao nhiêu. Chi phí chỉ số, biến tạm cố định là O(1), còn bản sao `clone()` dài `n` là O(n).

### Kiểm thử khả năng thích nghi

So sánh số phép so sánh/di chuyển cho các đầu vào **cùng độ dài**: tăng dần, gần sắp xếp, đảo ngược, có các runs dài. Đừng chỉ đo thời gian một lần, vì JIT, bộ nhớ đệm và nhiễu môi trường có thể che mất bản chất thuật toán.

Trong chương trình minh họa, ba mảng đều dài 6 nhưng số so sánh lần lượt là **5, 6, 15**; điều này phản ánh rõ khả năng insertion sort tận dụng đầu vào đã có thứ tự.

## 10. Sai lầm thường gặp

1. **Gọi “ổn định” là “không đổi vị trí phần tử”.** Stability chỉ yêu cầu giữ **thứ tự tương đối của các phần tử bằng khóa**, không giữ nguyên mọi chỉ số.
2. **Nhầm bằng nhau của bản ghi với bằng nhau của khóa.** Hai đối tượng khác nhau có thể bằng nhau theo comparator dùng để sắp xếp.
3. **Dùng `>=` trong vòng dịch insertion sort** rồi tuyên bố ổn định. Điều kiện này có thể đẩy bản ghi cũ có khóa bằng nhau ra sau bản ghi mới.
4. **Nghĩ swap tại chỗ đồng nghĩa ổn định.** Selection sort dùng swap là ví dụ không ổn định.
5. **Bỏ qua stack đệ quy** khi công bố O(1) bộ nhớ phụ cho một thuật toán đệ quy.
6. **Cho rằng cứ sửa mảng đầu vào là in-place.** Thuật toán vẫn có thể cấp thêm mảng đệm O(n).
7. **Tuyên bố merge sort thông thường luôn tại chỗ.** Cài đặt gộp chuẩn trên mảng thường dùng bộ đệm O(n), dù có các biến thể đặc biệt.
8. **Gắn tính thích nghi cho mọi phiên bản có cùng tên.** Bubble sort phải có tối ưu dừng sớm mới đạt O(n) ở dãy đã sắp trong cách cài đặt được mô tả.
9. **Nhầm best case và worst case.** Insertion sort O(n) trên dãy đã sắp nhưng vẫn O(n²) trên dãy đảo ngược.
10. **Xét một ví dụ rồi suy ra thuộc tính cho mọi đầu vào.** Tính ổn định là bảo đảm **với mọi đầu vào hợp lệ**; muốn bác bỏ chỉ cần một phản ví dụ, muốn chứng minh phải dựa trên bất biến/cơ chế thuật toán.
11. **Cho rằng Java `Arrays.sort` nào cũng có cùng bảo đảm.** Cần phân biệt overload cho mảng đối tượng với comparator và các overload cho mảng kiểu nguyên thủy; stability không có cùng ý nghĩa quan sát đối với các giá trị nguyên thủy trùng nhau.
12. **Chỉ ghi O(n log n) mà bỏ yêu cầu thực tế.** Có thể cần giữ thứ tự phụ, giảm bộ nhớ hoặc tận dụng dữ liệu đã gần sắp xếp hơn là chỉ tối ưu worst-case thời gian.

## 11. Bài tập tự luyện có lời giải

**Bài 1.** Sau sắp xếp tăng dần theo `score`, dữ liệu `[(3,X),(1,Y),(3,Z),(2,T)]` phải có dạng nào nếu thuật toán ổn định? **Lời giải:** `[(1,Y),(2,T),(3,X),(3,Z)]`. Hai bản ghi có khóa 3 giữ thứ tự `X` trước `Z`.

**Bài 2.** Với dãy `[(2,A),(2,B),(1,C)]`, phiên bản selection sort hoán đổi min với đầu đoạn có ổn định không? **Lời giải:** không; sau swap đầu tiên thành `[(1,C),(2,B),(2,A)]`, đảo thứ tự `A` và `B` dù khóa bằng nhau.

**Bài 3.** Vì sao insertion sort dịch khi `A[j] > chosen` mà không dịch khi bằng nhau? **Lời giải:** dừng ngay trước bản ghi bằng khóa cũ để chèn bản ghi mới sau nó, giữ thứ tự tương đối ban đầu và do đó ổn định.

**Bài 4.** Một thuật toán sửa trực tiếp `A`, nhưng tạo thêm `int[] buffer = new int[A.length]`. Có phải O(1) in-place không? **Lời giải:** không. Bộ đệm có kích thước O(n), dù `A` vẫn bị sửa.

**Bài 5.** Mảng số nguyên tăng dần dài 6 có bao nhiêu nghịch thế? Mảng giảm dần `[6,5,4,3,2,1]` có bao nhiêu? **Lời giải:** lần lượt `0` và `6·5/2=15`. Insertion sort có lượng dịch chuyển tăng tương ứng theo số nghịch thế.

**Bài 6.** Merge sort thông dụng dùng một mảng phụ dài `n` và ưu tiên nửa trái khi hai khóa bằng nhau. Nó có ổn định không, có tại chỗ O(1) không? **Lời giải:** ổn định nếu hai nửa cũng được sắp ổn định và cách gộp luôn lấy từ nửa trái khi hòa; **không** tại chỗ theo nghĩa O(1) vì dùng đệm O(n).

**Bài 7.** Bubble sort chỉ hoán đổi khi `left.key > right.key`, nhưng luôn chạy đủ số lượt cố định kể cả khi mảng đã sắp. Nó ổn định không, thích nghi với dãy đã sắp không? **Lời giải:** ổn định vì không đảo thứ tự hai phần tử bằng khóa; nhưng nếu không có dừng sớm, bản này không tận dụng tốt dãy đã sắp về số lượt so sánh.

**Bài 8.** Muốn sắp xếp theo `department` rồi theo `registrationTime` bằng hai lần sắp ổn định, cần chạy khóa nào trước? **Lời giải:** sắp ổn định theo tiêu chí phụ `registrationTime` trước, rồi sắp ổn định theo tiêu chí chính `department`. Lượt sau giữ trật tự của lượt trước trong từng nhóm cùng phòng ban.

**Bài 9.** Một phiên bản quicksort dùng đệ quy trên các đoạn con. Có được báo chắc chắn O(1) tổng bộ nhớ phụ vì bước partition dùng O(1) không? **Lời giải:** không. Phải tính stack đệ quy; độ sâu và cấu trúc chia quyết định bộ nhớ phụ tổng.

## 12. Checklist chọn thuật toán sắp xếp

Khi nhận một bài toán sắp xếp, hãy trả lời:

1. **Khóa so sánh là gì?** Khi hai phần tử “bằng nhau” theo khóa, có cần giữ thứ tự xuất hiện của chúng không?
2. **Đầu vào có được sửa không?** Thuật toán có được cấp O(n) vùng phụ hay phải giới hạn O(1) (tính cả stack)?
3. **Dữ liệu vốn có thứ tự tới đâu?** Có nhiều runs, ít nghịch thế hoặc gần tăng dần không?
4. **Thời gian cần bảo đảm ở mức nào?** Best-case, trung bình hay worst-case quan trọng?
5. **Độ lớn dữ liệu và chi phí ghi/so sánh ra sao?** Dữ liệu nhỏ có thể hợp insertion sort; dữ liệu lớn cần đánh giá thuật toán và API phù hợp.
6. **Có thể xác minh không?** Thử khóa trùng với nhãn phân biệt, mảng rỗng, một phần tử, dãy đã sắp, đảo ngược và nhiều giá trị bằng nhau.

**Ghi nhớ:** *ổn định* nói về **thứ tự tương đối khi bằng khóa**; *tại chỗ* nói về **bộ nhớ phụ**; *thích nghi* nói về **khả năng tận dụng thứ tự sẵn có của dữ liệu**. Xét ba thuộc tính riêng biệt mới giúp chọn đúng thuật toán sắp xếp cho yêu cầu thực tế.
