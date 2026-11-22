# Counting sort và miền khóa nguyên hữu hạn

## 1. Khi nào dùng Counting sort?

**Counting sort (sắp xếp bằng đếm)** là thuật toán sắp xếp phân phối dành cho dữ liệu có khóa là số nguyên thuộc một **miền hữu hạn** có thể cấp phát bộ đếm. Khác với sắp xếp dựa trên việc liên tục so sánh hai phần tử, Counting sort đếm tần suất từng khóa, xác định vùng kết quả dành cho khóa ấy rồi đưa phần tử vào đúng vị trí.

Ví dụ, cần sắp xếp các điểm số nguyên trong [0, 100] hoặc mã trạng thái từ 0 đến 9. Khi số lượng phần tử n lớn mà số khóa khả dĩ k nhỏ, phương pháp có thể rất hiệu quả: thời gian **Θ(n + k)** trong mô hình truy cập mảng O(1). Điều kiện này rất khác với lời hứa “mọi bài toán sắp xếp số nguyên đều tuyến tính”.

Counting sort cần hiểu rõ **khóa dùng để sắp xếp** và **miền khóa**:

- Một phần tử có thể chỉ là số nguyên như -2, 0, 5, hoặc một bản ghi như (key=2, tag="A").
- Khóa có thể âm; không cần bắt đầu tại 0.
- Các khóa phải nằm trong khoảng nguyên **[minKey, maxKey]** đã xác định.
- Độ rộng miền khóa là **k = maxKey − minKey + 1**, tính bằng phép toán đủ rộng để không tràn.
- Có thể có nhiều phần tử cùng khóa. Nếu chúng là các bản ghi khác nhau, cần quyết định có bảo toàn thứ tự ban đầu của chúng hay không.

| Thuộc tính | Counting sort với miền khóa hữu hạn |
| --- | --- |
| Đầu vào | n phần tử, mỗi phần tử có khóa nguyên |
| Điều kiện quan trọng | Biết được khoảng khóa và cấp phát được k bộ đếm |
| Cách làm | Đếm khóa → cộng dồn → đặt vào mảng kết quả |
| So sánh cặp khóa để sắp xếp | Không cần |
| Thời gian | Θ(n + k) cho phiên bản ổn định tạo mảng đầu ra |
| Bộ nhớ phụ | Θ(n + k) cho bản ghi, bao gồm mảng kết quả và bộ đếm |
| Tính ổn định | Có, nếu đặt phần tử theo đúng quy tắc |
| Tính tại chỗ | Phiên bản ổn định thông dụng không phải in-place |

**Lưu ý:** chữ k là **số giá trị nguyên khả dĩ trong cả khoảng**, kể cả các khóa không xuất hiện trong dữ liệu. Nếu chỉ có 5 phần tử nhưng khóa thuộc [0, 1.000.000.000], k vẫn bằng 1.000.000.001, nên cách tạo một bộ đếm cho mỗi khóa có thể không khả thi.

## 2. Hợp đồng đầu vào–đầu ra và các giả thiết

Xét bài toán sắp xếp tăng dần một mảng bản ghi, mỗi bản ghi có khóa int và một nhãn phân biệt giúp quan sát tính ổn định. Ta chọn hợp đồng:

1. Đầu vào là mảng Entry[] không null; mỗi phần tử Entry cũng không null.
2. Hai tham số minKey, maxKey là giới hạn miền khóa, yêu cầu minKey ≤ maxKey.
3. Mỗi khóa key thỏa minKey ≤ key ≤ maxKey.
4. Độ rộng k phải biểu diễn được bằng chỉ số mảng int và hệ thống phải có đủ bộ nhớ để cấp phát bộ đếm và đầu ra.
5. Mảng rỗng hợp lệ: trả một mảng mới rỗng.
6. Đầu ra là **một mảng mới**, được sắp xếp theo khóa tăng không giảm, có đủ đúng n bản ghi của đầu vào, không thêm hoặc bỏ bản ghi.
7. Với các phần tử có khóa bằng nhau, thứ tự tương đối trong đầu ra phải giống thứ tự trong đầu vào (**stable**).
8. Không thay đổi mảng đầu vào. Phiên bản Java sử dụng record bất biến để làm ví dụ.
9. Null gây NullPointerException; miền khóa không hợp lệ, quá rộng hoặc một khóa nằm ngoài miền gây IllegalArgumentException.

Các giới hạn bộ nhớ thực tế phụ thuộc máy và JVM. Dù k biểu diễn được bằng int, phép cấp phát int[k] vẫn có thể thất bại vì không đủ heap. Trong trường hợp đó, việc chọn Counting sort là không phù hợp về nguồn lực; cần chọn thuật toán khác hoặc giới hạn miền đầu vào.

Hậu điều kiện có thể phát biểu:

- **Có thứ tự:** với mọi i từ 1 đến n−1, output[i−1].key ≤ output[i].key.
- **Bảo toàn phần tử:** mỗi đối tượng bản ghi trong input xuất hiện trong output đúng số lần nó có trong input.
- **Ổn định:** với mọi i < j và input[i].key = input[j].key, nếu hai phần tử ấy được xét là hai lần xuất hiện riêng biệt, bản ghi tại i nằm trước bản ghi tại j trong output.
- **Bất biến đầu vào:** các phần tử tại từng vị trí input vẫn như trước khi gọi.

Không đủ khi chỉ kiểm tra mảng đầu ra đã tăng: một thuật toán làm mất bản ghi mà vẫn cho dãy tăng là sai hợp đồng.

## 3. Miền khóa hữu hạn và cách ánh xạ khóa âm

Counting sort cần chuyển mỗi giá trị khóa thành chỉ số hợp lệ trong mảng đếm. Với miền [minKey, maxKey] ta dùng:

~~~text
k = maxKey - minKey + 1
bucket(key) = key - minKey
0 <= bucket(key) < k
~~~

Ví dụ minKey = −2, maxKey = 2:

| Khóa | −2 | −1 | 0 | 1 | 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chỉ số bucket | 0 | 1 | 2 | 3 | 4 |

Không được dùng khóa âm trực tiếp làm chỉ số mảng Java. Cũng không được giả định minKey=0 khi dữ liệu chứa khóa âm. Việc **dịch gốc** bằng minKey vừa xử lý khóa âm vừa tránh lãng phí bộ đếm cho những giá trị thấp hơn miền thực tế.

**Bẫy tràn số:** minKey = Integer.MIN_VALUE, maxKey = Integer.MAX_VALUE. Về toán học:

~~~text
k = 2,147,483,647 - (-2,147,483,648) + 1
  = 4,294,967,296
~~~

Kết quả không chứa vừa một số int có dấu. Trong Java, phải tính bằng long **trước khi trừ**:

~~~java
long width = (long) maxKey - (long) minKey + 1L;
~~~

Chuyển sang long sau phép trừ int là quá muộn vì tràn đã xảy ra. Chỉ khi đã kiểm tra width > 0 và width đủ nhỏ mới ép sang int và tạo int[k]. Tương tự, chỉ số bucket nên tính bằng phép trừ long, rồi mới ép sang int sau khi xác minh khóa thuộc miền.

Nếu các khóa hiếm nằm cách xa nhau, ví dụ [-1.000.000.000, 1.000.000.000] chỉ có 3 phần tử, Counting sort dạng mảng đếm không phù hợp. Khi đó nên xem xét sắp xếp so sánh, nén tọa độ có chi phí riêng, hoặc cấu trúc Map tùy mục tiêu.

## 4. Ba giai đoạn của Counting sort ổn định

Với n bản ghi và k bucket, quy trình phổ biến gồm ba bước.

### Giai đoạn 1 — Đếm tần suất

Tạo counts[0..k) ban đầu toàn 0. Với mỗi phần tử x:

~~~text
counts[bucket(x.key)]++
~~~

Sau lượt này, counts[b] là **số lần** xuất hiện của khóa tương ứng với bucket b. Tính tổng tất cả counts[b] phải bằng n.

### Giai đoạn 2 — Tạo tổng tích lũy

Duyệt các bucket tăng dần:

~~~text
for b = 1 .. k-1:
    counts[b] = counts[b] + counts[b-1]
~~~

Sau bước này, counts[b] bằng **số phần tử có khóa không lớn hơn khóa ở bucket b**. Nó là chỉ số *ngay sau* vùng dành cho khóa b trong mảng kết quả (exclusive end).

Vì vậy, nếu counts[b]=r thì phần tử tiếp theo thuộc bucket b được đặt tại chỉ số r−1 theo quy ước 0-based.

### Giai đoạn 3 — Đặt phần tử theo thứ tự ngược

Duyệt mảng đầu vào từ phải sang trái:

~~~text
for i = n-1 downTo 0:
    b = bucket(input[i].key)
    counts[b] = counts[b] - 1
    output[counts[b]] = input[i]
~~~

Tại thời điểm đặt một phần tử, ta giảm counts[b] trước để lấy vị trí cuối chưa sử dụng dành cho khóa b. Đi từ **phải sang trái** bảo toàn thứ tự tương đối giữa các bản ghi cùng khóa, do phần tử xuất hiện muộn hơn được đặt vào vị trí bên phải.

Sau khi đặt xong, counts không còn biểu diễn prefix sum ban đầu. Chúng đã biến thành các con trỏ về **vị trí trống tiếp theo bên trái** của mỗi vùng khóa; không nên tiếp tục diễn giải counts như bảng tần suất.

## 5. Ví dụ từng bước: đếm, cộng dồn và phân phối

Xét năm bản ghi:

~~~text
Input (theo thứ tự xuất hiện):
[(2,A), (-1,B), (2,C), (0,D), (-1,E)]
minKey = -1
maxKey = 2
k = 4
~~~

Hai bản ghi có khóa 2 là A và C; hai bản ghi có khóa −1 là B và E. Một đầu ra **ổn định** phải giữ B trước E và A trước C.

### 5.1. Đếm tần suất

| Khóa | −1 | 0 | 1 | 2 |
| --- | ---: | ---: | ---: | ---: |
| Bucket | 0 | 1 | 2 | 3 |
| Tần suất | 2 | 1 | 0 | 2 |

Mảng tần suất: counts = [2, 1, 0, 2].

Lưu ý khóa 1 không xuất hiện, nhưng vẫn có bucket và tần suất 0.

### 5.2. Tổng tích lũy

Cộng dồn từ trái sang phải:

~~~text
Trước cộng dồn: [2, 1, 0, 2]
Sau cộng dồn:   [2, 3, 3, 5]
~~~

Ý nghĩa: có 2 phần tử có khóa ≤−1, 3 phần tử có khóa ≤0, 3 phần tử có khóa ≤1, và 5 phần tử có khóa ≤2. Do đó:

| Khóa | Vùng trong output (nửa mở) |
| --- | --- |
| −1 | [0, 2) |
| 0 | [2, 3) |
| 1 | [3, 3) — rỗng |
| 2 | [3, 5) |

Khoảng nửa mở [l, r) bao gồm l và loại r; số vị trí của khoảng là r−l.

### 5.3. Đặt phần tử từ phải sang trái

Bắt đầu output gồm 5 vị trí trống, counts=[2,3,3,5]:

| Lượt | Phần tử | Bucket | Vị trí sau --counts[bucket] | Trạng thái phần được đặt |
| ---: | --- | ---: | ---: | --- |
| 1 | (−1,E) | 0 | 1 | output[1] = E |
| 2 | (0,D) | 1 | 2 | output[2] = D |
| 3 | (2,C) | 3 | 4 | output[4] = C |
| 4 | (−1,B) | 0 | 0 | output[0] = B |
| 5 | (2,A) | 3 | 3 | output[3] = A |

Đầu ra cuối:

~~~text
[(-1,B), (-1,E), (0,D), (2,A), (2,C)]
~~~

Trong nhóm khóa −1, B vẫn trước E; trong nhóm khóa 2, A vẫn trước C. Đây là lợi ích quan trọng khi dùng Counting sort làm một bước của **Radix sort**: thứ tự từ các vòng sắp xếp trước phải được giữ đối với các khóa bằng nhau ở vòng hiện tại.

**Phản ví dụ khi duyệt sai chiều:** nếu vẫn dùng prefix end counts và giảm trước khi đặt, nhưng lại duyệt đầu vào **trái sang phải**, các phần tử cùng khóa sẽ bị đặt theo thứ tự ngược: với cặp (2,A) rồi (2,C), C có thể nằm trước A. Kết quả vẫn tăng theo khóa nhưng **không ổn định**.

## 6. Vì sao thuật toán đúng?

Có thể chứng minh qua ba bất biến.

### 6.1. Bất biến của bước đếm

Sau khi xử lý t phần tử đầu vào, counts[b] bằng số lần xuất hiện của bucket b trong đúng t phần tử đó. Lúc t=0 mọi bộ đếm bằng 0. Khi gặp phần tử mới ở bucket b, chỉ counts[b] tăng 1, nên bất biến được duy trì. Với t=n, counts là tần suất thật của toàn bộ dãy.

### 6.2. Bất biến của bước tổng tích lũy

Sau khi tính đến bucket b, counts[b] bằng tổng tần suất ban đầu của các bucket 0..b. Chứng minh bằng quy nạp: bucket 0 đúng ngay sau bước đếm; giả sử counts[b−1] là tổng các bucket trước, cộng counts[b] ban đầu tạo tổng đến b. Vì mọi tần suất không âm, dãy tổng tích lũy không giảm, và tổng cuối cùng bằng n.

Các giá trị tích lũy chia mảng đầu ra thành các vùng **không giao nhau, đúng kích thước**, sắp theo thứ tự khóa tăng dần. Một bucket có tần suất 0 tương ứng vùng rỗng.

### 6.3. Bất biến của bước đặt và tính ổn định

Trong khi duyệt đầu vào từ phải sang trái, đối với mỗi khóa b, các phần tử của khóa b đã xử lý được đặt đúng vào **các vị trí bên phải chưa dùng của vùng b**. counts[b] chỉ tới biên trái còn trống, do đó --counts[b] không vượt ra khỏi vùng.

Nếu hai bản ghi x=input[i] và y=input[j] có cùng khóa và i<j, thì y được gặp **trước** x trong lượt duyệt ngược và được đặt vào vị trí **bên phải**. Sau đó x được đặt ở vị trí nhỏ hơn. Vậy thứ tự x trước y được giữ.

Mỗi phần tử được đặt đúng một lần, vì mỗi lần đặt dùng một vị trí trống của vùng khóa, và tổng độ dài mọi vùng là n. Các vùng được sắp theo khóa nên kết quả tăng không giảm; không phần tử nào bị mất hay tạo thêm. Do chỉ đọc các tham chiếu từ input và ghi vào output mới, mảng input không bị sửa.

**Tổng kết chứng minh:** bộ đếm đúng → kích thước vùng đúng → phân phối đúng và ổn định. Thuật toán kết thúc vì ba lượt có số bước hữu hạn n, k−1 và n.

## 7. Java 17+: chương trình độc lập, ổn định và an toàn hơn với khóa âm

Chương trình minh họa sử dụng record **Entry(int key, String tag)**. Key là trường sắp xếp; tag giúp quan sát các phần tử cùng khóa có giữ nguyên thứ tự ban đầu hay không.

Lưu tên tệp **CountingSortFiniteKeys.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class CountingSortFiniteKeys {
    private CountingSortFiniteKeys() {}

    public record Entry(int key, String tag) {}

    /**
     * Returns a new array, sorted by key in nondecreasing order.
     * Equal-key entries retain their original relative order.
     *
     * Requires minKey <= maxKey, every Entry non-null,
     * every key in [minKey, maxKey], and an allocatable key domain.
     * An empty input array is valid.
     */
    public static Entry[] stableCountingSort(
            Entry[] input, int minKey, int maxKey) {
        Objects.requireNonNull(input, "input");

        if (minKey > maxKey) {
            throw new IllegalArgumentException("minKey > maxKey");
        }

        long width = (long) maxKey - (long) minKey + 1L;
        if (width > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("key domain too wide");
        }
        int k = (int) width;

        int[] ends = new int[k];

        // Phase 1: count every key.
        for (Entry entry : input) {
            Objects.requireNonNull(entry, "entry");

            long offset = (long) entry.key() - (long) minKey;
            if (offset < 0 || offset >= width) {
                throw new IllegalArgumentException("key outside domain");
            }
            ends[(int) offset]++;
        }

        // Phase 2: exclusive end of each key's segment.
        for (int bucket = 1; bucket < k; bucket++) {
            ends[bucket] += ends[bucket - 1];
        }

        Entry[] output = new Entry[input.length];

        // Phase 3: right-to-left placement makes the sort stable.
        for (int i = input.length - 1; i >= 0; i--) {
            Entry entry = input[i];
            int bucket = (int) ((long) entry.key() - (long) minKey);
            int position = --ends[bucket];
            output[position] = entry;
        }

        return output;
    }

    public static void main(String[] args) {
        Entry[] data = {
            new Entry(2, "A"),
            new Entry(-1, "B"),
            new Entry(2, "C"),
            new Entry(0, "D"),
            new Entry(-1, "E")
        };

        System.out.println("Input: " + Arrays.toString(data));
        System.out.println("Sorted: "
                + Arrays.toString(stableCountingSort(data, -1, 2)));
        System.out.println("Unchanged: " + Arrays.toString(data));

        System.out.println("Empty: "
                + Arrays.toString(stableCountingSort(new Entry[0], 0, 0)));

        Entry[] extreme = {
            new Entry(Integer.MIN_VALUE, "X"),
            new Entry(Integer.MIN_VALUE + 1, "Y")
        };
        System.out.println("Extreme: "
                + Arrays.toString(stableCountingSort(
                        extreme, Integer.MIN_VALUE,
                        Integer.MIN_VALUE + 1)));

        try {
            stableCountingSort(
                    new Entry[] {new Entry(3, "bad")}, 0, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid key: IllegalArgumentException");
        }

        try {
            stableCountingSort(
                    new Entry[0], Integer.MIN_VALUE, Integer.MAX_VALUE);
        } catch (IllegalArgumentException ex) {
            System.out.println("Wide domain: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac CountingSortFiniteKeys.java
java CountingSortFiniteKeys
~~~

Stdout dự kiến chính xác:

~~~text
Input: [Entry[key=2, tag=A], Entry[key=-1, tag=B], Entry[key=2, tag=C], Entry[key=0, tag=D], Entry[key=-1, tag=E]]
Sorted: [Entry[key=-1, tag=B], Entry[key=-1, tag=E], Entry[key=0, tag=D], Entry[key=2, tag=A], Entry[key=2, tag=C]]
Unchanged: [Entry[key=2, tag=A], Entry[key=-1, tag=B], Entry[key=2, tag=C], Entry[key=0, tag=D], Entry[key=-1, tag=E]]
Empty: []
Extreme: [Entry[key=-2147483648, tag=X], Entry[key=-2147483647, tag=Y]]
Invalid key: IllegalArgumentException
Wide domain: IllegalArgumentException
~~~

Java record tự tạo biểu diễn chuỗi dạng Entry[key=..., tag=...], do đó các dòng trên có thể dự kiến chính xác. Việc trả mảng mới không đổi input, đồng thời output vẫn chứa **chính các bản ghi Entry đã có**, không tạo bản ghi mới; vì Entry là record bất biến, đây là một ví dụ thuận lợi để giải thích phép sắp xếp ổn định.

Điều kiện "allocatable key domain" có ý nghĩa thực tế: code chặn width > Integer.MAX_VALUE nhưng **không thể bảo đảm** máy còn đủ heap cho mọi width nhỏ hơn ngưỡng này. Nếu k quá lớn so với RAM, cấp phát có thể gây OutOfMemoryError. Đối với ứng dụng thật, có thể đặt ngưỡng miền khóa an toàn theo ngân sách bộ nhớ và chọn thuật toán khác trước khi cấp phát.

## 8. Phân tích chi phí O(n+k) chính xác

Gọi n = input.length và k = maxKey−minKey+1.

- Tạo int[k] và khởi tạo 0: Θ(k).
- Đếm n bản ghi: Θ(n), mỗi lần truy cập bucket O(1).
- Cộng dồn k−1 bucket: Θ(k).
- Tạo mảng output dài n và đặt n bản ghi: Θ(n).
- Tổng: **Θ(n+k)** thời gian.

Đối với mã Java đã cho, bộ nhớ phụ gồm int[k] và Entry[n], nên **Θ(n+k)**. Chỉ tính vài biến đếm là O(1) sẽ bỏ qua mảng kết quả và bộ đếm, dẫn đến phát biểu sai về bộ nhớ.

Nếu chỉ cần sắp xếp **các giá trị số nguyên** và được phép ghi đè lên mảng đầu vào, có thể đếm khóa trong int[k], rồi viết lại mỗi khóa vào input số lần bằng tần suất. Biến thể này có thời gian Θ(n+k), bộ nhớ phụ Θ(k), nhưng không cho thấy **tính ổn định của các bản ghi cùng khóa** vì không giữ một đầu ra gồm bản ghi phân biệt. Không được lấy cận bộ nhớ Θ(k) của biến thể ghi đè để mô tả chương trình ổn định phía trên.

### 8.1. Khi nào gần tuyến tính theo n?

Khi **k = O(n)**, ta có n+k = O(n), vì thế Counting sort chạy Θ(n) theo kích thước đầu vào trong mô hình chi phí. Tuy nhiên, khi k lớn hơn n rất nhiều, thời gian khởi tạo và quét bộ đếm có thể chiếm ưu thế.

Ví dụ:

| n | Miền khóa | k | Nhận định |
| ---: | --- | ---: | --- |
| 100.000 | [0, 99] | 100 | Rất phù hợp với bộ đếm trực tiếp |
| 100.000 | [−500, 500] | 1.001 | Thường vẫn phù hợp |
| 10 | [0, 1.000.000] | 1.000.001 | Tốn công và bộ nhớ cho đa số bucket không dùng |
| 5 | [Integer.MIN_VALUE, Integer.MAX_VALUE] | 4.294.967.296 | Không thể tạo mảng đếm có số bucket này bằng int index trong Java |

Chi phí của việc tính min/max từ đầu vào cũng cần tính. Nếu miền không được cho sẵn, có thể duyệt n phần tử để tìm min và max trong O(n), kiểm tra tràn, sau đó chạy Counting sort. Tổng vẫn O(n+k); tuy nhiên lời gọi trên hai lượt đếm và một lượt tìm miền nếu tính vào toàn quy trình cần được báo cáo đúng. Không được ngầm coi minKey/maxKey là miễn phí khi chúng phải được xác định từ dữ liệu.

### 8.2. Vì sao không mâu thuẫn với cận Ω(n log n) của sorting?

Cận dưới Ω(n log n) quen thuộc áp dụng cho **thuật toán sắp xếp dựa trên so sánh** trên n khóa phân biệt trong mô hình quyết định bằng so sánh. Counting sort sử dụng **khả năng ánh xạ khóa nguyên sang một miền bucket** và đếm tần suất, nên vượt ra khỏi mô hình chỉ so sánh các khóa với nhau. Do đó Θ(n+k) không vi phạm cận dưới dành cho comparison sorting.

Đổi lại, Counting sort phải trả giá bằng bộ nhớ cho toàn miền khóa và chỉ dùng trực tiếp khi có khóa nguyên hữu hạn được ánh xạ hiệu quả.

## 9. Tính ổn định và ứng dụng trong Radix sort

Tính ổn định có nghĩa: với hai phần tử khác nhau x,y cùng khóa, nếu x xuất hiện trước y trong input thì x vẫn đứng trước y trong output. Nó quan trọng khi mỗi phần tử có nhiều trường, chẳng hạn:

~~~text
[(điểm=8, tên="An"), (điểm=5, tên="Bình"), (điểm=8, tên="Chi")]
~~~

Sắp xếp ổn định theo điểm cho [(5,Bình), (8,An), (8,Chi)] và giữ An trước Chi.

Trong Radix sort theo từng chữ số, nhất là LSD radix sort (từ chữ số kém quan trọng nhất đến quan trọng nhất), vòng sắp xếp theo chữ số sau **phải ổn định** để không phá thứ tự đã hình thành từ các chữ số trước. Counting sort ổn định theo chữ số 0..9 là một thành phần điển hình.

Không phải cứ dùng mảng counts là tự động ổn định. Tính ổn định đến từ **cách đặt phần tử**: prefix sum cho vùng kết quả, và đặt từ phải sang trái với phép giảm biên cuối. Nếu dùng phiên bản ghi đè các giá trị nguyên từ counts, không thể suy ra rằng nó bảo toàn thứ tự các payload khác nhau có cùng khóa.

Một đặc điểm khác cần nhắc: Counting sort khi áp dụng cho các bản ghi vẫn cần dữ liệu của chúng, không thể chỉ trả một danh sách tần suất nếu hợp đồng yêu cầu bảo toàn nhãn hoặc nội dung đi kèm khóa.

## 10. Trường hợp biên và tính an toàn dữ liệu

| Trường hợp | Quyết định trong ví dụ Java |
| --- | --- |
| Mảng rỗng | Hợp lệ, trả mảng mới rỗng; miền khóa vẫn phải hợp lệ |
| Một bản ghi | Trả mảng một phần tử, giống giá trị nhưng khác tham chiếu mảng |
| Tất cả cùng khóa | Có một bucket chứa n; giữ nguyên thứ tự bản ghi |
| Khóa âm | Dịch chỉ số bằng minKey với phép tính long |
| Có khóa vắng mặt | Bucket có tần suất 0, vùng đầu ra có độ dài 0 |
| minKey > maxKey | IllegalArgumentException |
| Khóa ngoài miền | IllegalArgumentException |
| input null hoặc bản ghi null | NullPointerException |
| Miền rộng hơn Integer.MAX_VALUE bucket | IllegalArgumentException |
| Miền hợp lệ nhưng heap không đủ | Cấp phát có thể thất bại; cần quyết định ngân sách riêng |

Các trường hợp cần đặc biệt cẩn thận:

**Tràn số khi cộng dồn:** mảng đầu vào Java có độ dài biểu diễn bằng int. Tổng tất cả tần suất là n, nên khi n là độ dài mảng thực tế, phép cộng dồn counts[b] không vượt quá n. Tuy nhiên công thức tính **k** vẫn phải dùng long như code.

**Miền cung cấp rộng hơn thực tế:** Nếu minKey/maxKey là cận bao rộng mà nhiều khóa bên trong không tồn tại, thuật toán vẫn đúng nhưng dùng tài nguyên theo k đã cho. Không được thay k bằng “số khóa xuất hiện” mà vẫn giữ thiết kế mảng đếm trực tiếp.

**Đầu vào có phần tử trùng:** Counts phải ghi số lần, không chỉ đánh dấu khóa “có/không”. Nếu thay counts[b] = 1 bằng một tập boolean thì sẽ mất số lượng bản ghi.

**Đối tượng chứa dữ liệu có thể thay đổi:** Bản sao output là mảng mới nhưng vẫn tham chiếu tới cùng đối tượng nguồn nếu dùng các lớp tham chiếu có thể sửa. Ví dụ dùng record bất biến làm rõ phạm vi không sửa; trong hệ thống thật phải phân biệt shallow copy với deep copy.

**Null và lỗi:** Không nên âm thầm bỏ qua bản ghi null để “cứ sắp xếp tiếp” nếu hợp đồng bảo toàn số bản ghi. Việc ném ngoại lệ ở ví dụ phù hợp với quy định input hợp lệ.

## 11. So sánh với các lựa chọn khác

| Thuật toán / cách làm | Ý tưởng | Thời gian điển hình hoặc bảo đảm | Khi phù hợp |
| --- | --- | --- | --- |
| Counting sort | Đếm khóa trong miền hữu hạn k | Θ(n+k) | Khóa nguyên, k đủ nhỏ |
| Merge sort | Chia và trộn | Θ(n log n) | Cần cận thời gian rõ ràng, không phụ thuộc miền khóa; có thể ổn định |
| Quick sort | Phân hoạch theo pivot | Trung bình Θ(n log n) với lựa chọn phù hợp; tệ nhất có thể Θ(n²) | Thường hiệu quả trong thực tế với cài đặt tốt |
| Radix sort | Sắp xếp theo chữ số/vị trí khóa | Phụ thuộc số lượt d và chi phí mỗi lượt, thường O(d(n+b)) với b bucket | Khóa có biểu diễn hữu hạn theo các chữ số |
| HashMap tần suất | Chỉ lưu khóa thực xuất hiện | O(n) kỳ vọng để đếm; **không** tạo ngay thứ tự tăng | Cần đếm mà miền khóa quá thưa |

Nếu n nhỏ nhưng k cực lớn, sắp xếp so sánh thường phù hợp hơn. Nếu chỉ cần tìm tần suất của mỗi khóa, dùng HashMap có thể tiết kiệm bộ nhớ so với một mảng k bucket, nhưng bản thân HashMap không bảo đảm thứ tự tăng của khóa; muốn xuất ra theo thứ tự cần có thêm bước khác.

Nếu miền khóa đã nhỏ và cố định (ví dụ các điểm 0..100), Counting sort tránh những phép so sánh phức tạp và rất dễ dự đoán. Tuy nhiên, hiệu năng thực nghiệm vẫn phụ thuộc JVM, chi phí cấp phát mảng và bộ nhớ đệm; không thể kết luận “Counting sort luôn nhanh hơn Merge sort” chỉ từ ký hiệu tiệm cận.

## 12. Kiểm thử đúng tính chất, không chỉ đúng số

Ví dụ đầu ra có thể trông tăng dần nhưng vẫn sai vì mất bản ghi hoặc đảo thứ tự các phần tử cùng khóa. Do đó, cần kiểm thử **ba tính chất**: có thứ tự, bảo toàn bản ghi, và ổn định.

| Input | Miền khóa | Kết quả cần xác nhận |
| --- | --- | --- |
| [] | [0,0] | [] |
| [(2,A)] | [2,2] | [(2,A)] |
| [(2,A),(-1,B),(2,C),(0,D),(-1,E)] | [−1,2] | [(-1,B),(-1,E),(0,D),(2,A),(2,C)] |
| [(5,A),(5,B),(5,C)] | [5,5] | A trước B trước C |
| [(-2,A),(0,B),(-1,C)] | [−2,0] | [(-2,A),(-1,C),(0,B)] |
| [(3,X)] | [0,2] | IllegalArgumentException |
| Không có mảng (null) | [0,0] | NullPointerException |
| [(Integer.MIN_VALUE,X),(Integer.MIN_VALUE+1,Y)] | [MIN,MIN+1] | Hai phần tử đúng thứ tự |
| [] | [Integer.MIN_VALUE,Integer.MAX_VALUE] | IllegalArgumentException vì k quá rộng |

Để kiểm thử tự động:

1. Sinh các bản ghi có khóa ngẫu nhiên từ một miền nhỏ, gắn tag hoặc số thứ tự tăng theo vị trí gốc.
2. Chạy Counting sort và một lời giải tham chiếu **ổn định** (ví dụ thư viện sắp xếp đối tượng với Comparator theo key) trên dữ liệu tương đương.
3. So sánh từng bản ghi theo cả key và tag, không chỉ so sánh dãy key.
4. Đối chiếu rằng mỗi tham chiếu trong input xuất hiện đúng số lần trong output và input không đổi.
5. Lặp với mảng rỗng, một phần tử, tất cả cùng khóa, nhiều khóa vắng mặt, khóa âm, giới hạn int và miền không hợp lệ.

**Kiểm thử thuộc tính:** với mọi i>0, output[i−1].key ≤ output[i].key; với mọi cặp xuất hiện cùng khóa, thứ tự tương đối phải giữ; length(output) = length(input); có thể dùng bảng đếm theo tag để kiểm tra không mất dữ liệu.

Thư viện Java dùng Arrays.sort(Object[], Comparator) là sắp xếp ổn định theo tài liệu Java SE; khi dùng làm oracle, Comparator phải chỉ so sánh key, để thứ tự tag trong các nhóm cùng khóa được bảo toàn. Không nên dùng Arrays.sort(int[]) để làm bằng chứng cho tính ổn định của các bản ghi, vì các giá trị int trùng nhau không mang nhãn để quan sát thứ tự tương đối.

## 13. Những lỗi thường gặp

1. **Tuyên bố O(n) vô điều kiện.** Counting sort có chi phí Θ(n+k), và k có thể cực lớn dù n nhỏ.
2. **Giả định khóa bắt đầu từ 0.** Khóa âm gây chỉ số âm; phải ánh xạ bằng key−minKey.
3. **Tính k bằng int rồi ép sang long.** Phép trừ có thể tràn trước khi chuyển; ép các toán hạng sang long trước.
4. **Quên +1 ở k.** Miền đóng [minKey,maxKey] có maxKey−minKey+1 giá trị.
5. **Dùng counts như danh sách tần suất sau khi đã cộng dồn.** Prefix sums có nghĩa khác và sẽ tiếp tục biến đổi khi đặt phần tử.
6. **Quên giảm counts[b] trước khi gán output.** Khi counts[b] là exclusive end, chỉ số hợp lệ cuối cùng là counts[b]−1.
7. **Duyệt đầu vào từ trái sang phải với con trỏ cuối của bucket.** Có thể đảo thứ tự các bản ghi cùng khóa, phá tính ổn định.
8. **Chỉ lưu số lần xuất hiện mà bỏ mất bản ghi.** Với dữ liệu có payload, đầu ra phải chứa đúng từng bản ghi, không chỉ các khóa.
9. **Bỏ qua phần tử null hoặc khóa ngoài miền.** Làm thay đổi ý nghĩa kết quả mà không có quy định trong hợp đồng.
10. **Không tính mảng output vào bộ nhớ phụ.** Phiên bản ổn định trong ví dụ dùng Θ(n+k), không phải Θ(k).
11. **Cấp phát mảng theo miền int cực rộng.** Miền hữu hạn về mặt toán học chưa đủ; phải thực tế cấp phát được.
12. **Nhầm với sắp xếp so sánh.** Cận Ω(n log n) của mô hình so sánh không áp dụng nguyên xi cho counting sort với khóa nguyên hữu hạn.
13. **Đo thời gian chỉ trên một bộ dữ liệu.** Hãy kiểm tra tính đúng trước, rồi đo với nhiều n, k và phân phối khóa khác nhau.

## 14. Checklist quyết định sử dụng Counting sort

- [ ] Dữ liệu có một khóa nguyên hoặc mã hóa thành khóa nguyên rõ ràng?
- [ ] Miền [minKey,maxKey] được xác định đúng, kể cả số âm, và k được tính an toàn?
- [ ] Có đủ RAM cho k bộ đếm và n vị trí đầu ra?
- [ ] Cần giữ payload và tính ổn định của các bản ghi cùng khóa?
- [ ] Nếu yêu cầu ổn định, đã dùng prefix sum và duyệt ngược từ phải sang trái?
- [ ] Mảng rỗng, một phần tử, khóa ngoài miền, null và miền quá rộng đã có chính sách?
- [ ] Có kiểm thử thứ tự, bảo toàn phần tử, thứ tự tương đối và đầu vào không đổi?
- [ ] Đã báo cáo đúng Θ(n+k) thời gian và Θ(n+k) bộ nhớ phụ cho phiên bản ổn định?
- [ ] Nếu phát hiện miền khóa quá thưa, có kế hoạch dùng thuật toán khác?
- [ ] Nếu Counting sort nằm trong Radix sort, từng lượt đã bảo đảm ổn định?

**Ý chính:** Counting sort hiệu quả nhờ khai thác **miền khóa nguyên hữu hạn và đủ nhỏ**. Tần suất cho biết *có bao nhiêu phần tử mỗi khóa*; tổng tích lũy cho biết *vùng đầu ra của mỗi khóa*; đặt từ phải sang trái bảo đảm *ổn định*. Chỉ khi nêu rõ miền k, bộ nhớ cần dùng và cách bảo toàn bản ghi, lời khẳng định Θ(n+k) mới phản ánh đúng thuật toán.
