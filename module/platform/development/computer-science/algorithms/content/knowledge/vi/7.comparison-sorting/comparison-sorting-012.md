# Natural merge sort, Timsort và khai thác các đoạn đã có thứ tự

Một mảng thực tế hiếm khi hoàn toàn ngẫu nhiên. Nó có thể đã gần tăng dần, gồm nhiều đoạn được sắp xếp sẵn, được nối từ nhiều nguồn đã có thứ tự hoặc vừa có một số phần tử được chỉnh sửa. **Natural merge sort** và **TimSort** khai thác cấu trúc này để giảm việc sắp xếp lại từ đầu.

Trong nhóm **sắp xếp so sánh (comparison sorting)**, hai cách tiếp cận cần phân biệt:

- **Merge sort chia cố định:** chia mảng thành hai nửa theo chỉ số, sắp xếp từng nửa rồi gộp; thường thực hiện O(n log n) công việc dù đầu vào đã tăng dần nếu triển khai không nhận diện trật tự sẵn có.
- **Natural merge sort:** nhận diện các đoạn liên tiếp đã có thứ tự, gọi là **runs**, rồi gộp những đoạn này.
- **TimSort:** thuật toán sắp xếp ổn định, có khả năng thích nghi, kết hợp ý tưởng **natural runs**, **binary insertion sort** cho các run ngắn, chính sách gộp các run trên một ngăn xếp và tối ưu gộp như **galloping**. Đây không đơn thuần là đổi tên merge sort.

Bài học giải thích cơ chế, điều kiện ổn định, bất biến, độ phức tạp và cách đọc một cài đặt Java 17+ minh họa. Chương trình Java đầy đủ bên dưới **cài đặt natural merge sort đơn giản**; phần TimSort được trình bày đúng theo ý tưởng thuật toán, **không giả nhận chương trình đó là cài đặt TimSort**.

## 1. Run là gì và vì sao phát hiện run có ích?

Một **run** là đoạn liên tiếp của mảng vốn đã có thứ tự theo bộ so sánh. Với khóa số nguyên và thứ tự tăng dần, một run không giảm thỏa:

`A[i].key ≤ A[i+1].key` cho mọi cặp kề nhau trong run.

Ví dụ:

```text
Mảng:         [1, 3, 5, 2, 4, 6, 7]
Run thứ nhất: [1, 3, 5]
Run thứ hai:           [2, 4, 6, 7]
Kết quả gộp:  [1, 2, 3, 4, 5, 6, 7]
```

Thay vì chia cố định thành nhiều phần nhỏ không cần thiết, thuật toán có thể phát hiện **hai run đã tăng dần** và chỉ cần gộp chúng. Nếu toàn mảng đã tăng dần, nó là **một run**; không cần thêm lượt gộp.

Có hai hướng phát hiện thường gặp:

1. **Run không giảm (ascending/non-decreasing):** các khóa có thể bằng nhau; duyệt khi `previous ≤ next`.
2. **Run giảm nghiêm ngặt (strictly descending):** các khóa phải thực sự giảm; duyệt khi `previous > next`, rồi đảo ngược run để biến thành không giảm.

Với thuật toán sắp xếp **ổn định**, từ khóa **nghiêm ngặt** rất quan trọng. Giả sử đầu vào là `[(3,A),(3,B),(2,C)]`, so sánh chỉ theo khóa số. Nếu coi toàn đoạn là một run “không tăng” rồi đảo ngược, ta thu `[(2,C),(3,B),(3,A)]`: hai khóa 3 đổi thứ tự `A` và `B`, làm mất ổn định. Nếu chỉ đảo các run **giảm nghiêm ngặt**, hai bản ghi bằng khóa không thuộc cùng đoạn bị đảo, và thứ tự của chúng vẫn có thể được giữ qua phép gộp ổn định.

### Run tự nhiên và run cố định khác nhau thế nào?

Một thuật toán merge sort **bottom-up** cơ bản có thể bắt đầu với mỗi phần tử là một run độ dài 1, rồi gộp thành độ dài 2, 4, 8… Nó không tận dụng đầy đủ các đoạn có thứ tự đã tồn tại. Natural merge sort thay bước chia cố định bằng **quét mảng để phát hiện độ dài run thực tế**. Số run ban đầu, gọi là `r`, phản ánh phần nào mức độ có thứ tự của dữ liệu.

Lưu ý: không phải cứ ít run là luôn có ít so sánh hơn trong mọi cài đặt. Kết quả còn phụ thuộc cách **lựa chọn cặp run để gộp** và cách triển khai thao tác merge.

## 2. Gộp hai run ổn định bằng hai con trỏ

Giả sử hai đoạn liền nhau `A[left .. mid)` và `A[mid .. right)` đã được sắp xếp không giảm. Ta dùng hai con trỏ `i=left`, `j=mid` và vùng đệm `temp` để xuất lần lượt phần tử nhỏ hơn.

```text
ALGORITHM STABLE_MERGE(A, temp, left, mid, right)
    i <- left
    j <- mid
    k <- left

    WHILE i < mid AND j < right DO
        IF KEY(A[i]) <= KEY(A[j]) THEN
            temp[k] <- A[i]
            i <- i + 1
        ELSE
            temp[k] <- A[j]
            j <- j + 1
        END IF
        k <- k + 1
    END WHILE

    COPY all remaining items from the left run into temp
    COPY all remaining items from the right run into temp
    COPY temp[left .. right) back to A[left .. right)
END ALGORITHM
```

**Điểm quyết định ổn định:** khi hai khóa **bằng nhau**, chọn phần tử ở **run trái trước** nhờ dấu `≤`. Các phần tử trong từng run đã có thứ tự ổn định; ưu tiên run trái giữ nguyên quan hệ xuất hiện trước–sau giữa hai run. Nếu thay `≤` bằng `<`, ta có thể lấy phần tử ở run phải trước một phần tử bằng khóa ở run trái và làm mất tính ổn định.

**Bất biến khi gộp:** `temp[left .. k)` chứa đúng `k-left` phần tử nhỏ nhất đã lấy từ hai run, theo thứ tự không giảm và giữ thứ tự tương đối giữa các khóa bằng nhau. Sau mỗi bước, ít nhất một con trỏ tiến; khi một run hết, chép phần còn lại của run kia là đủ.

Một lần gộp hai run có tổng độ dài `m` dùng **O(m)** thời gian, vì mỗi phần tử được đọc/ghi hữu hạn lần. Với cách dùng bộ đệm thông thường, không gian phụ cho thao tác gộp có thể lên tới O(m), và chương trình minh họa cấp sẵn đệm O(n) cho toàn bộ mảng.

## 3. Natural merge sort: quy trình và bất biến

Phiên bản dễ hiểu có thể dùng các bước:

1. Quét từ trái sang phải, nhận diện các run không giảm hoặc giảm **nghiêm ngặt**; đảo các run giảm nghiêm ngặt để chúng trở thành không giảm.
2. Lưu **ranh giới cuối** của từng run, tính theo khoảng nửa mở `[start,end)`.
3. Gộp từng cặp run liền kề từ trái sang phải để tạo các run lớn hơn. Nếu cuối lượt còn một run lẻ, giữ nguyên nó sang lượt tiếp theo.
4. Lặp bước 3 cho đến khi chỉ còn một run bao phủ toàn mảng.

Giả mã cấp cao:

```text
ALGORITHM NATURAL_MERGE_SORT(A)
    runs <- DETECT_AND_NORMALIZE_RUNS(A)

    WHILE COUNT(runs) > 1 DO
        nextRuns <- empty list

        FOR EACH adjacent pair of runs (L, R) DO
            STABLE_MERGE(A, buffer, L.start, L.end, R.end)
            ADD merged run [L.start, R.end) TO nextRuns
        END FOR

        IF an unpaired last run exists THEN
            ADD that run TO nextRuns
        END IF

        runs <- nextRuns
    END WHILE
END ALGORITHM
```

Đây là giả mã minh họa thuật toán, không phải mã của một ngôn ngữ lập trình cụ thể. `DETECT_AND_NORMALIZE_RUNS` phải đảo chỉ các run giảm **nghiêm ngặt** nếu cần bảo toàn tính ổn định.

**Bất biến ở mức run:** trước mỗi lượt gộp, các run liền nhau trong danh sách bao phủ toàn bộ mảng, không chồng lấn, và từng run đã được sắp xếp **ổn định theo các phần tử xuất phát từ run đó**. Gộp hai run với quy tắc lấy phần tử run trái trước khi bằng khóa duy trì tính không giảm và thứ tự tương đối. Run chưa có cặp vẫn giữ nguyên. Khi còn một run, toàn mảng được sắp xếp ổn định.

**Tính kết thúc:** nếu đang có `r>1` run, sau một lượt chỉ còn `ceil(r/2)` run, nhỏ hơn `r`; cuối cùng có đúng một run.

### Ví dụ hai lượt gộp

Giả sử sau bước nhận diện có bốn run:

```text
R1 = [1, 4, 8]
R2 = [2, 6]
R3 = [0, 5, 9]
R4 = [3, 7]

Lượt 1:
merge(R1,R2) = [1, 2, 4, 6, 8]
merge(R3,R4) = [0, 3, 5, 7, 9]

Lượt 2:
merge([1,2,4,6,8], [0,3,5,7,9])
    = [0,1,2,3,4,5,6,7,8,9]
```

Không cần chia từng run về kích thước 1 như phiên bản bottom-up cơ bản. Tuy nhiên, một lần gộp vẫn phải đọc/ghi các phần tử của vùng được gộp; nhận diện run không có nghĩa toàn bộ phép sắp xếp là O(r).

## 4. Độ phức tạp của natural merge sort theo số run

Gọi `n` là số phần tử và `r` là số run được phát hiện sau bước quét ban đầu.

- **Nhận diện và chuẩn hóa run:** O(n) thời gian vì quét và đảo từng phần tử tối đa một số lần hằng định.
- **Số vòng gộp:** O(log r) với chính sách ghép các run cạnh nhau thành cặp qua từng lượt.
- **Chi phí mỗi vòng:** O(n) ở trường hợp cần gộp gần như toàn bộ các phần tử trong vòng đó.
- **Tổng thời gian:** **O(n(1 + log r))** cho phiên bản gộp cặp theo lượt được mô tả; vì `1 ≤ r ≤ n` khi `n > 0`, trường hợp xấu nhất là **O(n log n)**.
- **Bộ nhớ phụ:** O(n) nếu sử dụng mảng đệm gộp và danh sách/ranh giới run có kích thước tuyến tính.

Khi **toàn mảng đã không giảm**, `r=1`, chỉ cần quét và không phải gộp, nên O(n). Khi **toàn mảng giảm nghiêm ngặt**, có thể nhận diện một run rồi đảo nó trong O(n); thuật toán vẫn kết thúc sau bước đó. Các bản ghi bằng khóa phá một run giảm nghiêm ngặt thành các đoạn riêng để không bị đảo nhầm; chúng vẫn được gộp đúng và ổn định.

Cận O(n(1+log r)) ở đây dựa trên **cách gộp cặp tương đối cân bằng theo số lượt**, không phải bảo đảm cho mọi chiến lược gộp tùy tiện. Nếu liên tục gộp một run lớn với một run rất nhỏ theo thứ tự bất lợi mà không có chính sách tốt, tổng lượng phần tử được chép lại có thể tăng đáng kể.

## 5. TimSort tận dụng run như thế nào?

**TimSort** (cũng thường viết **Timsort**) là thuật toán sắp xếp ổn định, thích nghi, nổi bật trong các thư viện sắp xếp dữ liệu đối tượng. Nó có cùng trực giác **nhận diện run tự nhiên rồi gộp**, nhưng bổ sung các kỹ thuật nhằm hiệu quả trên nhiều loại dữ liệu.

### 5.1. Nhận diện run tăng và giảm

TimSort tìm một đoạn tăng **không giảm** hoặc giảm **nghiêm ngặt** và đảo đoạn giảm. Nhờ không đảo chuỗi có hai phần tử bằng khóa, thuật toán giữ được khả năng ổn định.

Ví dụ bản ghi:

```text
Đầu vào: [(5,A), (4,B), (3,C), (3,D), (7,E)]
Run giảm: [(5,A), (4,B), (3,C)] -> [(3,C), (4,B), (5,A)]
Run tiếp: [(3,D), (7,E)] giữ nguyên
Gộp ổn định: [(3,C), (3,D), (4,B), (5,A), (7,E)]
```

Bản ghi `(3,C)` vẫn đứng trước `(3,D)`, đúng thứ tự đầu vào. Nếu đảo một run **không tăng** chứa cả hai bản ghi khóa 3, kết quả có thể sai về ổn định.

### 5.2. minRun và insertion sort

Một mảng có rất nhiều run dài 1–2 phần tử sẽ khiến việc quản lý và gộp những run rất ngắn kém hiệu quả. TimSort chọn một độ dài run tối thiểu có kiểm soát, thường gọi là **minRun**. Với các mảng đủ dài, các triển khai kinh điển thường chọn minRun quanh **32–64** (phụ thuộc kích thước đầu vào và hiện thực); với mảng rất nhỏ, cách xử lý có thể khác.

Nếu run tự nhiên ngắn hơn mức dự định, thuật toán **mở rộng run** bằng cách sắp xếp thêm các phần tử sát bên, thường dùng **binary insertion sort**:

- Dùng tìm kiếm nhị phân xác định vị trí chèn trong phần run đã có thứ tự.
- Dịch các phần tử để mở chỗ, nhờ đó giữ tính ổn định.
- Tìm vị trí chèn có thể cần O(log m) phép so sánh, **nhưng vẫn có thể phải dịch O(m) phần tử** cho mỗi lần chèn. Không nên kết luận binary insertion sort trở thành O(n log n) tổng thời gian chỉ vì có tìm kiếm nhị phân.

Bước này đặc biệt phù hợp khi các run đã gần có thứ tự hoặc chỉ cần bổ sung ít phần tử để đạt độ dài mong muốn.

### 5.3. Ngăn xếp run và chính sách gộp

TimSort thường duy trì các run liên tiếp trên một **stack**, gồm điểm đầu và độ dài mỗi run. Nó không nhất thiết gộp các cặp từ trái qua phải theo vòng như natural merge sort giản lược. Thay vào đó, thuật toán kiểm tra các **điều kiện cân bằng về độ dài run** rồi quyết định lúc nào gộp để tránh các chuỗi thao tác bất lợi.

Trong các mô tả TimSort cổ điển có những bất biến về quan hệ giữa độ dài của ba run gần đỉnh stack, ví dụ các điều kiện đủ mạnh để tránh gộp mất cân đối. **Chi tiết bất biến và chính sách merge có thể khác nhau giữa các hiện thực/phiên bản**, nên không nên viết một bộ bất đẳng thức duy nhất như một hợp đồng API bất biến của mọi TimSort.

Nguyên tắc thiết kế cần nhớ: **run đã có thứ tự được lưu có cấu trúc, và thời điểm gộp được lựa chọn có chủ đích**. Đây là điểm khác biệt cốt lõi với mô hình chỉ có “đếm run rồi gộp tuần tự”.

### 5.4. Galloping: tìm và sao chép theo khối khi phù hợp

Trong merge thông thường, mỗi bước so sánh phần tử đầu hai run rồi chép một phần tử. Nếu một run liên tục đưa ra phần tử nhỏ hơn run kia, TimSort có thể chuyển sang chế độ **galloping**: dùng tìm kiếm tăng khoảng cách (kiểu exponential search) rồi xác định ranh giới, sau đó chép một đoạn phù hợp thay vì chỉ xử lý từng phần tử một.

Ví dụ khi một run chứa rất nhiều giá trị nhỏ hơn phần tử đầu của run kia, galloping có thể tiết kiệm các phép so sánh. Nhưng galloping cũng có chi phí thiết lập; không phải luôn tốt hơn merge từng phần tử. Những hiện thực thực tế có thể điều chỉnh ngưỡng kích hoạt theo hành vi dữ liệu.

Galloping **không thay đổi yêu cầu ổn định**: xử lý khóa bằng nhau phải tuân theo quy tắc giữ thứ tự tương đối trước–sau của các phần tử nguồn.

### 5.5. Tính chất hiệu năng của TimSort

Ở mức thuật toán, TimSort được thiết kế có **O(n log n) thời gian trong trường hợp xấu nhất** và có thể chạy gần **O(n)** trên dữ liệu đã có thứ tự. Với bộ đệm gộp trong những hiện thực phổ biến, bộ nhớ phụ có thể tăng đến **O(n)** trong trường hợp xấu nhất. Tính ổn định vẫn là một yêu cầu độc lập với mức sử dụng bộ nhớ.

Java có các API sắp xếp mảng đối tượng như `Arrays.sort(T[], Comparator)`, trong đó **tính ổn định là bảo đảm API**. Một số triển khai JDK dùng các thuật toán trong họ TimSort cho trường hợp này, nhưng **không nên viết chương trình phụ thuộc vào tên thuật toán nội bộ, minRun cố định, chiến lược merge hay galloping của một phiên bản JDK**. Các overload sắp xếp mảng kiểu nguyên thủy là một trường hợp khác; với giá trị nguyên thủy bằng nhau, tính ổn định thường không quan sát được vì không có nhãn đối tượng đi kèm.

## 6. Java 17+: một natural merge sort ổn định có thể chạy

Chương trình minh họa dưới đây thực hiện:

1. Phát hiện các run tăng không giảm hoặc giảm **nghiêm ngặt**.
2. Đảo từng run giảm nghiêm ngặt.
3. Gộp các run liền nhau theo cặp, với bộ đệm tạm.
4. Lặp cho đến một run duy nhất.

Để quan sát tính ổn định, mỗi phần tử có **khóa số nguyên** và **nhãn gốc**. So sánh chỉ theo khóa; nhãn chỉ cho thấy các phần tử bằng khóa có còn đúng thứ tự ban đầu hay không. Hàm `naturalMergeSort` trả về số run **ban đầu**, chỉ để kiểm tra khả năng khai thác cấu trúc dữ liệu; nó vẫn sửa trực tiếp mảng truyền vào và sử dụng O(n) bộ nhớ phụ.

Tạo tệp **`NaturalMergeDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class NaturalMergeDemo {
    record Item(int key, String label) {
        @Override
        public String toString() {
            return "(" + key + "," + label + ")";
        }
    }

    public static int naturalMergeSort(Item[] a) {
        Objects.requireNonNull(a, "array");
        int n = a.length;
        if (n == 0) {
            return 0;
        }

        // ends[j]: chỉ số kết thúc loại trừ của run thứ j.
        int[] ends = new int[n];
        int runCount = 0;
        int start = 0;

        while (start < n) {
            int end = start + 1;

            if (end < n) {
                if (a[start].key() <= a[end].key()) {
                    while (end < n &&
                            a[end - 1].key() <= a[end].key()) {
                        end++;
                    }
                } else {
                    // Chỉ đảo run giảm NGHIÊM NGẶT.
                    while (end < n &&
                            a[end - 1].key() > a[end].key()) {
                        end++;
                    }
                    reverse(a, start, end);
                }
            }

            ends[runCount++] = end;
            start = end;
        }

        int originalRuns = runCount;
        Item[] temp = new Item[n];

        while (runCount > 1) {
            int nextCount = 0;
            int from = 0;

            for (int j = 0; j < runCount; j += 2) {
                int mid = ends[j];

                if (j + 1 < runCount) {
                    int to = ends[j + 1];
                    merge(a, temp, from, mid, to);
                    ends[nextCount++] = to;
                    from = to;
                } else {
                    // Run lẻ cuối cùng chuyển sang lượt sau.
                    ends[nextCount++] = mid;
                    from = mid;
                }
            }

            runCount = nextCount;
        }

        return originalRuns;
    }

    private static void reverse(Item[] a, int from, int to) {
        int i = from;
        int j = to - 1;
        while (i < j) {
            Item temp = a[i];
            a[i] = a[j];
            a[j] = temp;
            i++;
            j--;
        }
    }

    private static void merge(Item[] a, Item[] temp,
                              int from, int mid, int to) {
        int i = from;
        int j = mid;
        int k = from;

        while (i < mid && j < to) {
            // Khi bằng khóa, lấy bên trái để ổn định.
            if (a[i].key() <= a[j].key()) {
                temp[k++] = a[i++];
            } else {
                temp[k++] = a[j++];
            }
        }

        while (i < mid) {
            temp[k++] = a[i++];
        }
        while (j < to) {
            temp[k++] = a[j++];
        }

        System.arraycopy(temp, from, a, from, to - from);
    }

    public static void main(String[] args) {
        Item[] mixed = {
            new Item(5, "A"), new Item(4, "B"),
            new Item(3, "C"), new Item(3, "D"),
            new Item(7, "E"), new Item(6, "F"),
            new Item(2, "G"), new Item(2, "H"),
            new Item(8, "I")
        };
        System.out.println("runs=" + naturalMergeSort(mixed));
        System.out.println("sorted=" + Arrays.toString(mixed));

        Item[] ordered = {
            new Item(1, "X"), new Item(2, "Y"),
            new Item(2, "Z"), new Item(5, "W")
        };
        System.out.println("orderedRuns=" +
                naturalMergeSort(ordered));
        System.out.println("ordered=" + Arrays.toString(ordered));

        Item[] decreasing = {
            new Item(4, "P"), new Item(3, "Q"),
            new Item(2, "R"), new Item(1, "S")
        };
        System.out.println("descendingRuns=" +
                naturalMergeSort(decreasing));
        System.out.println("descending=" +
                Arrays.toString(decreasing));

        Item[] ties = {
            new Item(2, "A"), new Item(2, "B"),
            new Item(1, "C")
        };
        System.out.println("tieRuns=" +
                naturalMergeSort(ties));
        System.out.println("ties=" + Arrays.toString(ties));
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac NaturalMergeDemo.java
java NaturalMergeDemo
```

Đầu ra:

```text
runs=4
sorted=[(2,G), (2,H), (3,C), (3,D), (4,B), (5,A), (6,F), (7,E), (8,I)]
orderedRuns=1
ordered=[(1,X), (2,Y), (2,Z), (5,W)]
descendingRuns=1
descending=[(1,S), (2,R), (3,Q), (4,P)]
tieRuns=2
ties=[(1,C), (2,A), (2,B)]
```

**Đọc kết quả:**

- Mảng `mixed` có bốn run tự nhiên khi phát hiện theo quy tắc trên. Hai bản ghi khóa `2` giữ thứ tự `G` trước `H`; hai bản ghi khóa `3` giữ `C` trước `D`, chứng tỏ phép đảo run giảm và phép gộp không phá tính ổn định.
- `ordered` có một run, kể cả hai bản ghi bằng khóa `2`; thuật toán chỉ quét, không cần lượt gộp.
- `decreasing` là một run giảm nghiêm ngặt, được đảo thành dãy tăng dần ngay khi phát hiện.
- `ties=[(2,A),(2,B),(1,C)]` tách thành hai run, rồi gộp để được `[(1,C),(2,A),(2,B)]`. Nếu đảo cả một run không tăng chứa hai khóa `2`, `A` và `B` có thể bị đổi thứ tự sai.

Hàm `merge` **đọc** từ hai run đã sắp và **ghi** vào `temp`; nó ưu tiên run trái khi khóa bằng nhau. Sau khi chép về `a`, một run đã gộp vẫn có thứ tự để tham gia lượt sau. Trong `naturalMergeSort`, mảng `ends` ghi các cận cuối loại trừ; sau mỗi lượt, các cận được nén ngay trên cùng mảng vì những phần tử `ends` đã đọc từ trái qua phải không còn cần giữ nguyên ở vị trí cũ.

**Điều kiện đầu vào:** `a` không được `null`, và các phần tử trong mảng phải là `Item` khác `null`; chương trình không xử lý trường hợp có phần tử `null`. Mảng rỗng được chấp nhận và hàm trả số run 0. Không có yêu cầu `label` phải duy nhất để thuật toán sắp theo khóa, nhưng nhãn phân biệt làm kết quả kiểm tra stability dễ quan sát.

## 7. Natural merge sort so với TimSort và các thuật toán khác

| Thuật toán/biến thể | Phát hiện run tự nhiên? | Ổn định? | Best-case | Worst-case | Bộ nhớ phụ điển hình |
| --- | --- | --- | --- | --- | --- |
| **Merge sort bottom-up cơ bản** | Không, bắt đầu từ độ dài cố định | Có nếu merge ưu tiên bên trái khi bằng | O(n log n) theo cách cài đặt cố định | O(n log n) | O(n) với buffer |
| **Natural merge sort gộp run theo cặp** | Có | Có nếu đảo chỉ run giảm nghiêm ngặt và merge ổn định | O(n) khi một run | O(n log n) | O(n) với buffer và ranh giới |
| **TimSort** | Có | Có | O(n) trên dữ liệu thuận lợi | O(n log n) | Có thể đến O(n) |
| **Insertion sort** (dịch khi khóa lớn hơn) | Khai thác thứ tự cục bộ, không cần danh sách run | Có | O(n) | O(n²) | O(1) |
| **Heap sort thông dụng** | Không | Không | O(n log n) | O(n log n) | O(1) với triển khai heap mảng không đệ quy |

Bảng trên nói về các **phiên bản tiêu chuẩn được nêu**. Một thuật toán có thể có những biến thể khác với tính ổn định, cơ chế bộ nhớ và tối ưu khác. Đặc biệt, **TimSort không phải natural merge sort gộp cặp**: nó bổ sung minRun, insertion sort để hoàn thiện run ngắn, chính sách merge stack và galloping.

Một số vấn đề thực tế cần cân nhắc:

- **Tính ổn định:** cần thiết khi sắp nhiều khóa theo các lượt khác nhau hoặc giữ trật tự trước đó giữa bản ghi có cùng khóa.
- **Tính thích nghi:** có lợi với mảng đang tăng dần, giảm nghiêm ngặt hoặc chứa các run dài.
- **Bộ nhớ:** merge dựa trên buffer thường cần nhiều bộ nhớ hơn heap sort hoặc insertion sort tại chỗ.
- **Chi phí so sánh và sao chép:** với bản ghi lớn hoặc comparator đắt, một phép so sánh có thể tốn đáng kể; galloping và chiến lược gộp có thể ảnh hưởng hiệu năng.
- **Đặc tả API:** khi dùng thư viện, cần dựa vào cam kết ổn định và kết quả sắp xếp thay vì dựa vào chi tiết nội bộ như ngưỡng minRun.

## 8. Các sai lầm thường gặp

1. **Nhận diện run giảm bằng `>=` rồi đảo:** đảo hai bản ghi bằng khóa có thể phá ổn định. Run đảo phải giảm **nghiêm ngặt**.
2. **Merge lấy phần tử từ phải khi hai khóa bằng nhau:** làm thay đổi thứ tự gốc của các phần tử bằng khóa nằm ở hai run.
3. **Nhầm “mảng có nhiều run” với “mảng đã sắp xếp”:** mỗi run chỉ có thứ tự **bên trong**, chưa bảo đảm toàn bộ mảng không giảm.
4. **Gộp run bất kỳ không xét thứ tự xuất hiện:** phải gộp những run **liền kề** và giữ trật tự nguồn khi muốn ổn định.
5. **Coi số run ban đầu là toàn bộ chi phí:** một lần merge phải xử lý các phần tử trong vùng gộp; cần cộng chi phí qua nhiều lượt.
6. **Cho rằng mọi natural merge sort chắc chắn O(n log r):** cận này cần chính sách gộp có kiểm soát; gộp mất cân đối kéo dài có thể gây chi phí xấu hơn.
7. **Nói binary insertion sort có O(n log n) thời gian vì dùng tìm kiếm nhị phân:** tìm vị trí có thể ít so sánh nhưng **dịch phần tử vẫn tốn thời gian**.
8. **Áp dụng ngưỡng minRun cố định cho mọi TimSort:** giá trị và cách sử dụng phụ thuộc kích thước dữ liệu, phiên bản và hiện thực.
9. **Coi galloping luôn nhanh hơn merge bình thường:** khi dữ liệu xen kẽ mạnh, chi phí tìm kiếm và chuyển chế độ có thể không có lợi.
10. **Tuyên bố natural merge sort đơn giản chính là TimSort:** thiếu các chính sách run-stack, minRun và galloping.
11. **Quên đệm phụ:** merge sort dùng mảng tạm kích thước O(n) không phải in-place O(1).
12. **Không phân biệt thứ tự so sánh và danh tính:** với các khóa trùng nhau, cần nhãn hoặc chỉ số gốc để kiểm chứng ổn định.
13. **Phân tích độ phức tạp chỉ theo `n`:** để thấy tính thích nghi nên xét thêm số run `r` và đặc điểm các đoạn đã có thứ tự.
14. **Dựa vào thuật toán cụ thể bên trong `Arrays.sort`:** API có bảo đảm hành vi; tên hiện thực và các tối ưu bên trong có thể thay đổi.

## 9. Tự kiểm tra và lời giải

**Câu 1.** Mảng `[1,3,5,2,4,6,7]` có những run không giảm tự nhiên nào? **Trả lời:** `[1,3,5]` và `[2,4,6,7]`. Gộp hai run thu `[1,2,3,4,5,6,7]`.

**Câu 2.** Vì sao không được đảo cả đoạn `[(3,A),(3,B),(2,C)]` như một run giảm nếu yêu cầu ổn định? **Trả lời:** đoạn có hai khóa bằng nhau `3`; đảo nó làm `B` đứng trước `A`. Phải chỉ đảo những run **giảm nghiêm ngặt**.

**Câu 3.** Với hai run `[(1,A),(3,B)]` và `[(3,C),(4,D)]`, khi gộp ổn định bản ghi khóa 3 xuất hiện theo thứ tự nào? **Trả lời:** `(3,B)` rồi `(3,C)`, vì bản ghi của run trái có vị trí gốc đứng trước và phép merge chọn trái khi hòa.

**Câu 4.** Nếu `n=1000` và chỉ có `r=1` run tự nhiên, độ phức tạp của natural merge sort gộp cặp là gì? **Trả lời:** O(n) để quét/phát hiện, không cần lượt merge. Không cần tính O(n log n) cho trường hợp đầu vào này.

**Câu 5.** Nếu có `r=8` run và mỗi lượt gộp theo cặp, tối đa cần bao nhiêu lượt để còn một run? **Trả lời:** ba lượt: `8→4→2→1`; chi phí từng lượt còn phụ thuộc tổng độ dài run được gộp.

**Câu 6.** Tại sao TimSort có thể tận dụng dữ liệu gần sắp xếp tốt hơn merge sort chia nửa cố định? **Trả lời:** nhận diện các run có sẵn, mở rộng run ngắn khi phù hợp, lên lịch gộp có kiểm soát và có thể tận dụng galloping khi một run thắng liên tiếp.

**Câu 7.** Binary insertion sort trong TimSort dùng tìm kiếm nhị phân; vậy chèn vào mảng mất O(log n) thời gian không? **Trả lời:** không. Xác định vị trí có thể O(log n) **so sánh**, nhưng phải dịch nhiều phần tử, nên một lần chèn vẫn có thể O(n) thời gian.

**Câu 8.** Một hàm tự viết sắp bản ghi theo khóa, có những khóa bằng nhau nhưng sau sắp nhãn bị đổi thứ tự; hàm có ổn định không? **Trả lời:** không, dù khóa cuối cùng vẫn tăng dần. Kiểm tra stability phải dựa trên thứ tự tương đối của những phần tử bằng khóa.

**Câu 9.** Nếu cần một lời gọi thư viện Java đảm bảo ổn định cho mảng đối tượng với comparator, có thể dùng gì? **Trả lời:** `Arrays.sort(array, comparator)`. Nên dựa vào bảo đảm **ổn định của API**, không phụ thuộc một triển khai minRun cụ thể.

**Câu 10.** Khi có hai run gốc với phần tử cuối run trái bằng phần tử đầu run phải, tại sao có thể gộp chúng mà không phải hoán đổi các phần tử bằng nhau? **Trả lời:** với `leftKey ≤ rightKey`, toàn đoạn có thể đã là một run không giảm; nếu vẫn thực hiện merge ổn định thì quy tắc chọn run trái khi hòa vẫn giữ thứ tự. Việc phát hiện và bỏ qua những merge không cần thiết là một tối ưu riêng.

## 10. Checklist chọn và cài đặt cách sắp xếp khai thác run

Trước khi chọn natural merge sort, TimSort hay một thuật toán sắp khác, hãy kiểm tra:

1. **Dữ liệu có nhiều đoạn đã tăng/giảm hay không?** Xem cả trường hợp đã sắp và các run không giảm dài.
2. **Có cần ổn định không?** Xác định comparator và kiểm tra với bản ghi có cùng khóa nhưng nhãn khác nhau.
3. **Phát hiện chiều run ra sao?** Run tăng cho phép `≤`, run giảm đem đảo phải dùng `>` nghiêm ngặt.
4. **Chính sách gộp có kiểm soát không?** Gộp cặp theo lượt dễ chứng minh; TimSort dùng run stack và những điều kiện chọn merge thích hợp.
5. **Bộ nhớ phụ nào được phép?** Buffer gộp O(n) khác với thuật toán tại chỗ O(1).
6. **Tính đúng được chứng minh chưa?** Mỗi run có thứ tự, merge ổn định, các run vẫn phủ kín mảng và số run giảm đến một.
7. **Chi phí có xét tính thích nghi chưa?** Ngoài `n`, quan tâm `r` và phân bố độ dài run.
8. **Kiểm thử biên đủ chưa?** Mảng rỗng, một phần tử, đã sắp, giảm nghiêm ngặt, toàn phần tử bằng nhau, nhiều khóa trùng, nhiều run ngắn và số lượng phần tử lớn.

**Ghi nhớ:** natural merge sort bắt đầu từ **những đoạn đã có thứ tự**, thay vì coi mọi phần tử là hoàn toàn chưa sắp. TimSort phát triển ý tưởng đó bằng các quyết định thông minh về **độ dài run**, **thời điểm gộp** và **cách gộp**. Cả hai đều dựa vào quy tắc ổn định ở các khóa bằng nhau và vào bất biến “mỗi run đã có thứ tự” để xây dựng kết quả đúng.
