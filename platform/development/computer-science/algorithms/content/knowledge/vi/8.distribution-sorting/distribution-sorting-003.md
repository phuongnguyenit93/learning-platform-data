# Tính ổn định trong cách xây dựng kết quả counting sort

**Counting sort** (sắp xếp đếm) là thuật toán sắp xếp dựa trên phân phối: đếm số lần xuất hiện của từng khóa trong một miền giá trị rời rạc, rồi xác định vị trí đích của mỗi phần tử. Với khóa nguyên trong miền không quá lớn, thuật toán có thể đạt thời gian **\(O(n+R)\)**, trong đó \(n\) là số phần tử và \(R\) là số giá trị khóa có thể có. Nhưng **đếm đúng tần suất chưa đủ để đảm bảo sắp xếp ổn định**. Tính ổn định phụ thuộc vào cách cấp vị trí trong mảng kết quả và **hướng duyệt đầu vào**.

Bài học tập trung vào yêu cầu “**Tính ổn định trong cách xây dựng kết quả counting sort**”: thế nào là ổn định, cách biến tần suất thành biên của từng nhóm khóa, vì sao công thức đặt phần tử đi từ **phải sang trái** thường được sử dụng, một biến thể đi từ **trái sang phải** cũng ổn định, cách chứng minh và kiểm thử với những bản ghi có khóa trùng nhau.

## 1. Counting sort sắp xếp điều gì?

Giả sử có \(n\) bản ghi, mỗi bản ghi gồm:

- **Khóa** (key): trường dùng để so sánh thứ tự, ví dụ điểm số hoặc mức ưu tiên.
- **Dữ liệu đi kèm** (payload, satellite data): tên, mã, thời điểm nhận, đối tượng gốc.

Ví dụ đầu vào theo thứ tự xuất hiện:

\[
[(2,A),(1,B),(2,C),(0,D),(1,E),(2,F)].
\]

Số 2, 1, 0 là khóa; các chữ A, B, ... là mã riêng của từng bản ghi. Mục tiêu là sắp xếp tăng theo khóa. Một đầu ra **ổn định** là:

\[
[(0,D),(1,B),(1,E),(2,A),(2,C),(2,F)].
\]

Ba bản ghi có khóa 2 phải vẫn đứng theo thứ tự **A, C, F**, vì đó là thứ tự ban đầu giữa các bản ghi có **cùng khóa**. Hai bản ghi khóa 1 vẫn đứng theo thứ tự **B, E**.

### Định nghĩa hình thức

Thuật toán sắp xếp theo khóa \(key(x)\) được gọi là **ổn định** (*stable*) nếu với mọi cặp vị trí đầu vào \(i<j\):

\[
key(a[i])=key(a[j])
\ \Longrightarrow\
position_{\text{output}}(a[i])
<
position_{\text{output}}(a[j]).
\]

Tức là các phần tử **bằng khóa nhưng không nhất thiết bằng toàn bộ dữ liệu** vẫn giữ được thứ tự tương đối. Nếu chỉ sắp xếp các số nguyên không có dữ liệu đi kèm, ta khó quan sát sự khác biệt giữa thuật toán ổn định và không ổn định, vì hai số 2 giống hệt nhau về giá trị. Do đó, để kiểm tra tính ổn định hãy gắn **nhãn định danh** hoặc thứ tự nguồn vào từng phần tử.

Tính ổn định đặc biệt hữu ích khi sắp xếp theo **nhiều khóa**, ví dụ trước tiên sắp xếp theo tên rồi sắp xếp **ổn định** theo lớp: các phần tử cùng lớp sẽ vẫn giữ thứ tự tên từ bước trước. Nó cũng là điều kiện cơ bản của **radix sort theo chữ số từ phải sang trái (LSD)**: mỗi lượt phân phối theo chữ số phải ổn định để không phá thứ tự đã tạo bởi các chữ số ít quan trọng hơn.

## 2. Phần đếm tần suất chỉ xác định số lượng

Giả sử khóa thuộc miền nguyên liên tiếp \(\{min,min+1,\ldots,max\}\). Đặt

\[
R=max-min+1,\qquad idx(key)=key-min.
\]

Mảng \`count[0..R-1]\` ban đầu bằng 0. Với mỗi bản ghi có khóa \`key\`, tăng \`count[idx(key)]\` một đơn vị.

Ví dụ khóa đầu vào \([2,1,2,0,1,2]\), miền \([0,2]\):

| Khóa | 0 | 1 | 2 |
|---|---:|---:|---:|
| Tần suất | 1 | 2 | 3 |

Từ tần suất, ta biết đầu ra sẽ có **một** phần tử khóa 0, **hai** phần tử khóa 1 và **ba** phần tử khóa 2. Nhưng nếu chỉ lặp in ra \`0,1,1,2,2,2\`, ta đã **làm mất thông tin A–F**; không thể xác định hai bản ghi khóa 1 hay ba bản ghi khóa 2 có còn đúng thứ tự hay không.

Để sắp xếp bản ghi một cách ổn định, ta cần đưa **từng bản ghi gốc** vào đúng vị trí trong mảng kết quả. Việc này sử dụng **tổng tiền tố của tần suất**.

## 3. Từ tần suất đến biên kết thúc từng nhóm khóa

Gọi \`freq[v]\` là tần suất của khóa tương ứng vị trí v trong mảng đếm. Tính tổng tiền tố:

\[
C[v]=\sum_{u=0}^{v}freq[u].
\]

Đây là **số bản ghi có khóa không lớn hơn khóa v**. Do đó, trong mảng đầu ra dùng chỉ số 0-based:

- \`C[v]\` là **biên phải loại trừ** (*exclusive end*) của nhóm khóa v.
- Vị trí cuối cùng của nhóm này là \`C[v]-1\`.
- Vị trí đầu tiên của nhóm này là \`C[v-1]\` khi v>0; với v=0, vị trí đầu là 0.

Ví dụ với tần suất [1,2,3]:

| Khóa | \`freq\` | \`C\` (tổng tiền tố) | Vị trí dành riêng trong đầu ra |
|---|---:|---:|---|
| 0 | 1 | 1 | Chỉ số 0 |
| 1 | 2 | 3 | Chỉ số 1, 2 |
| 2 | 3 | 6 | Chỉ số 3, 4, 5 |

Mảng tổng tiền tố ở đây là **[1,3,6]**. Chúng ta có thể coi \`C[v]\` là một con trỏ chỉ vị trí **ngay sau ô trống cuối cùng** còn lại của nhóm khóa v. Khi đặt một bản ghi vào nhóm này, giảm \`C[v]\` trước rồi đặt bản ghi tại \`output[C[v]]\`:

~~~text
C[v] = C[v] - 1
output[C[v]] = bản_ghi
~~~

Đây là nguyên lý xây dựng kết quả counting sort ổn định trong phiên bản **duyệt đầu vào từ phải sang trái**.

## 4. Quy trình chuẩn: duyệt đầu vào từ phải sang trái

Bốn pha chính của counting sort ổn định (sắp tăng theo khóa):

1. **Đếm tần suất:** số phần tử có từng khóa.
2. **Tính tổng tiền tố:** biến mỗi tần suất thành biên phải loại trừ của vùng dành cho khóa đó.
3. **Đặt phần tử:** đi qua đầu vào **từ cuối về đầu**. Với bản ghi \`x\`, chọn v tương ứng khóa, giảm \`C[v]\` rồi ghi \`output[C[v]] = x\`.
4. **Trả mảng kết quả:** các vùng khóa đã được lấp đầy theo thứ tự tăng; trong mỗi vùng, thứ tự bằng khóa giữ nguyên như đầu vào.

Mã giả:

~~~text
stableCountingSort(input):
    nếu input rỗng: trả mảng rỗng

    tìm min, max và xác định miền R = max - min + 1
    tạo count[0..R-1] bằng 0

    for mỗi bản ghi x trong input:
        count[x.key - min]++

    for v = 1 .. R - 1:
        count[v] += count[v - 1]

    tạo output[0..n-1]

    for i = n - 1 .. 0:
        x = input[i]
        v = x.key - min
        count[v]--
        output[count[v]] = x

    return output
~~~

**Điểm thiết yếu:** sau pha tổng tiền tố, \`count[v]\` không còn đại diện cho tần suất chưa thay đổi; nó là **con trỏ vị trí ghi** của nhóm khóa v và sẽ giảm dần khi xây dựng kết quả. Nếu cần dùng lại tần suất ban đầu, hãy giữ bản sao hoặc tính một mảng biên riêng.

### Mô phỏng sáu bản ghi

Đầu vào: \`[2:A, 1:B, 2:C, 0:D, 1:E, 2:F]\`. Tần suất \`[1,2,3]\`; tổng tiền tố ban đầu \`C=[1,3,6]\`. Bắt đầu từ bản ghi cuối F.

| Lượt duyệt ngược | Khóa | Con trỏ nhóm sau khi giảm | Ô đầu ra được ghi |
|---|---:|---:|---|
| F | 2 | \`C[2]=5\` | \`output[5]=2:F\` |
| E | 1 | \`C[1]=2\` | \`output[2]=1:E\` |
| D | 0 | \`C[0]=0\` | \`output[0]=0:D\` |
| C | 2 | \`C[2]=4\` | \`output[4]=2:C\` |
| B | 1 | \`C[1]=1\` | \`output[1]=1:B\` |
| A | 2 | \`C[2]=3\` | \`output[3]=2:A\` |

Mảng kết quả cuối cùng:

~~~text
Chỉ số:  0    1    2    3    4    5
Bản ghi: 0:D  1:B  1:E  2:A  2:C  2:F
~~~

Trong nhóm khóa 2, F được xét trước và được xếp ở vị trí **cuối** nhóm; C được xếp trước F, rồi A được xếp trước C. Nhờ đó thứ tự A–C–F được bảo toàn.

## 5. Chứng minh tính ổn định

Cần chứng minh cả **thứ tự tăng theo khóa** lẫn **thứ tự tương đối của các bản ghi bằng khóa**.

### 5.1. Các khóa khác nhau không xen lẫn

Sau khi đếm và tính tổng tiền tố, mỗi khóa v được cấp một đoạn vị trí liên tục riêng:

\[
start(v)\le position < end(v).
\]

Trong đó \`end(v)=C[v]\` trước pha đặt phần tử, còn \`start(v)=0\` nếu v=0 và bằng \`C[v-1]\` nếu v>0. Các đoạn này có độ dài đúng bằng tần suất của khóa và xếp nối tiếp theo thứ tự tăng khóa. Khi đặt đúng \`freq[v]\` bản ghi của khóa v vào vùng của v, những bản ghi khóa nhỏ hơn luôn đứng trước những bản ghi khóa lớn hơn.

### 5.2. Hai bản ghi cùng khóa giữ thứ tự

Xét hai bản ghi \`input[i]\` và \`input[j]\` có cùng khóa v với \`i<j\`. Khi duyệt từ phải sang trái, thuật toán xử lý \`input[j]\` **trước** \`input[i]\`. Cả hai dùng chung con trỏ \`C[v]\`. Mỗi lần đặt một bản ghi v, con trỏ giảm đúng một đơn vị.

Vì \`input[j]\` được đặt trước, nó nhận một **chỉ số đầu ra lớn hơn**; khi tới \`input[i]\`, con trỏ đã giảm nên bản ghi trước đó được đặt vào **chỉ số nhỏ hơn**. Do đó:

\[
position_{\text{output}}(input[i])
<
position_{\text{output}}(input[j]).
\]

Đây chính là định nghĩa tính ổn định.

### 5.3. Mỗi phần tử được ghi đúng một lần

Tần suất quyết định chính xác số ô trong từng nhóm. Mỗi bản ghi đầu vào được duyệt đúng một lần và làm giảm một con trỏ đúng một lần; mỗi lần ghi sử dụng một ô chưa dùng ở trong nhóm được cấp. Hai nhóm khác khóa có đoạn riêng, hai bản ghi cùng khóa nhận hai chỉ số khác nhau vì con trỏ giảm. Sau n lần ghi, mỗi ô đầu ra đều được lấp đầy.

**Kết luận chứng minh:** mảng đầu ra được sắp xếp tăng theo khóa, không mất/nhân đôi bản ghi, và giữ thứ tự ban đầu giữa mọi cặp bản ghi có cùng khóa.

## 6. Lỗi phổ biến: duyệt xuôi nhưng vẫn dùng biên cuối

Giả sử giữ nguyên tổng tiền tố \`C=[1,3,6]\` và công thức:

~~~text
C[v]--
output[C[v]] = x
~~~

nhưng đổi vòng đặt phần tử từ **phải sang trái** thành **trái sang phải**. Khi đó phần tử cùng khóa xuất hiện **trước** lại được xếp ở ô **cuối** trong nhóm, nên thứ tự của nhóm bị đảo.

Đối với ba bản ghi khóa 2 xuất hiện theo thứ tự A, C, F:

| Duyệt xuôi | Vị trí nhận được trong nhóm 2 |
|---|---:|
| A được đặt trước | 5 |
| C được đặt tiếp | 4 |
| F được đặt cuối | 3 |

Nhóm khóa 2 trong đầu ra lúc này trở thành **F, C, A**. Các khóa vẫn có thể được sắp tăng, số lượng từng khóa vẫn đúng, nhưng thuật toán **không ổn định**.

Trên ví dụ sáu bản ghi, kết quả duyệt xuôi với con trỏ cuối là:

~~~text
[0:D, 1:E, 1:B, 2:F, 2:C, 2:A]
~~~

Nếu chỉ nhìn dãy khóa \`[0,1,1,2,2,2]\`, người học dễ nhầm rằng kết quả đã hoàn toàn đúng. Dùng nhãn A–F cho thấy thứ tự bản ghi khóa 1 và khóa 2 đã bị đảo. **Tính ổn định phải được kiểm tra trên dữ liệu có bản ghi phân biệt, không chỉ so sánh dãy giá trị khóa.**

Cũng không được tùy tiện chuyển duyệt ngược sang một biến thể khác mà không điều chỉnh con trỏ vị trí. **Hướng duyệt và kiểu con trỏ phải là một cặp nhất quán.**

## 7. Biến thể ổn định khác: duyệt xuôi với biên bắt đầu

Duyệt ngược không phải là cách **duy nhất** để bảo toàn thứ tự. Ta có thể dùng **con trỏ ô trống đầu tiên** của mỗi nhóm khóa, rồi đi qua đầu vào **từ trái sang phải**.

Từ mảng tần suất \`freq[0..R-1]\`, tính:

\[
start[0]=0,\qquad
start[v]=\sum_{u=0}^{v-1}freq[u]\quad(v>0).
\]

Khi đọc bản ghi x có khóa v từ trái sang phải:

~~~text
output[start[v]] = x
start[v]++
~~~

Mỗi bản ghi có khóa v được ghi vào ô trống đầu tiên của nhóm; bản ghi tới trước luôn nhận chỉ số nhỏ hơn. Vì vậy biến thể này cũng **ổn định**, với cùng độ phức tạp \(O(n+R)\).

| Hướng duyệt đầu vào | Con trỏ trong nhóm khóa | Cập nhật vị trí | Có ổn định không? |
|---|---|---|---|
| **Phải → trái** | Biên cuối loại trừ \`end[v]\` | \`output[--end[v]]=x\` | **Có** |
| **Trái → phải** | Biên đầu \`start[v]\` | \`output[start[v]++]=x\` | **Có** |
| Trái → phải | Biên cuối loại trừ \`end[v]\` | \`output[--end[v]]=x\` | Không, đảo thứ tự bằng khóa |
| Phải → trái | Biên đầu \`start[v]\` | \`output[start[v]++]=x\` | Không, đảo thứ tự bằng khóa |

Điều cần nhớ là **tính ổn định xuất phát từ thứ tự cấp ô đích trong từng nhóm**, không phải từ tên “counting sort” hay bản thân thao tác đếm.

## 8. Java 17+: counting sort ổn định cho bản ghi

Chương trình sau sắp xếp mảng **Entry** gồm \`key\` (khóa nguyên có thể âm) và \`id\` (nhãn để quan sát thứ tự). Sử dụng tổng tiền tố và duyệt từ phải sang trái. Dữ liệu đầu vào được giữ nguyên, kết quả là một mảng mới.

Để hỗ trợ khóa âm và tránh tràn trong phép \`max-min+1\`, chương trình tính chiều dài miền khóa bằng **long** rồi mới chuyển về int. Tuy nhiên counting sort vẫn yêu cầu miền khóa có kích thước đủ nhỏ để cấp phát mảng đếm; kiểm tra phù hợp với khả năng RAM là điều kiện sử dụng của thuật toán.

Lưu thành tệp **StableCountingSortDemo.java**:

~~~java
import java.util.Objects;
import java.util.StringJoiner;

public class StableCountingSortDemo {
    record Entry(int key, String id) {}

    static Entry[] stableCountingSort(Entry[] input) {
        Objects.requireNonNull(input, "input");

        if (input.length == 0) {
            return new Entry[0];
        }

        Entry first = Objects.requireNonNull(input[0], "entry 0");
        int min = first.key();
        int max = first.key();

        for (int i = 0; i < input.length; i++) {
            Entry entry = Objects.requireNonNull(input[i], "entry " + i);
            int key = entry.key();
            if (key < min) {
                min = key;
            }
            if (key > max) {
                max = key;
            }
        }

        long domainSize = (long) max - (long) min + 1L;
        if (domainSize > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("key range too large");
        }

        int range = (int) domainSize;
        int[] count = new int[range];

        // 1) Frequencies, with an offset for negative keys.
        for (Entry entry : input) {
            int v = (int) ((long) entry.key() - (long) min);
            count[v]++;
        }

        // 2) Inclusive prefix counts = exclusive group ends.
        for (int v = 1; v < range; v++) {
            count[v] += count[v - 1];
        }

        // 3) Place records from right to left.
        Entry[] output = new Entry[input.length];
        for (int i = input.length - 1; i >= 0; i--) {
            Entry entry = input[i];
            int v = (int) ((long) entry.key() - (long) min);
            int destination = --count[v];
            output[destination] = entry;
        }
        return output;
    }

    static String describe(Entry[] entries) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (Entry entry : entries) {
            result.add(entry.key() + ":" + entry.id());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        Entry[] data = {
            new Entry(2, "A"),
            new Entry(1, "B"),
            new Entry(2, "C"),
            new Entry(0, "D"),
            new Entry(1, "E"),
            new Entry(2, "F")
        };

        System.out.println("Input: " + describe(data));
        System.out.println("Sorted: "
            + describe(stableCountingSort(data)));

        Entry[] negative = {
            new Entry(-2, "X"),
            new Entry(0, "Y"),
            new Entry(-2, "Z"),
            new Entry(-1, "W")
        };
        System.out.println("Negative keys: "
            + describe(stableCountingSort(negative)));

        Entry[] equal = {
            new Entry(5, "P"),
            new Entry(5, "Q")
        };
        System.out.println("Equal keys: "
            + describe(stableCountingSort(equal)));

        System.out.println("Empty: "
            + describe(stableCountingSort(new Entry[0])));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac StableCountingSortDemo.java
java StableCountingSortDemo
~~~

**Kết quả stdout:**

~~~text
Input: [2:A, 1:B, 2:C, 0:D, 1:E, 2:F]
Sorted: [0:D, 1:B, 1:E, 2:A, 2:C, 2:F]
Negative keys: [-2:X, -2:Z, -1:W, 0:Y]
Equal keys: [5:P, 5:Q]
Empty: []
~~~

**Giải thích tính ổn định trong mã:** \`destination = --count[v]\` lấy ô cuối chưa sử dụng của nhóm khóa v. Vòng đặt phần tử chạy với \`i--\` từ cuối về đầu, cho nên hai bản ghi bằng khóa như \`2:A\` và \`2:C\` nhận ô theo thứ tự ngược lúc xử lý nhưng đúng thứ tự trong mảng kết quả: A đứng trước C. Tương tự, X đứng trước Z dù cả hai có khóa -2. Chương trình giữ nguyên chính các **tham chiếu bản ghi Entry** thay vì dựng bản ghi mới; mọi nhãn gắn với khóa vẫn đi cùng đúng phần tử.

**Kiểu int và long:** nếu viết \`int range = max - min + 1\` trực tiếp, hiệu có thể tràn int khi khóa có giá trị rất âm và rất dương. Ở đây \`(long)max - (long)min + 1L\` thực hiện phép tính trong long trước, nên phát hiện miền lớn hơn Integer.MAX_VALUE. Ngay cả một miền hợp lệ về số học vẫn có thể không đủ RAM để cấp phát; giới hạn bộ nhớ cần được áp dụng ở tầng gọi phù hợp với hệ thống.

**Xử lý null:** \`input == null\` và phần tử \`input[i] == null\` bị từ chối bằng \`NullPointerException\` có thông báo. Đối với mảng rỗng, hàm trả một mảng rỗng ngay mà không yêu cầu phải có khóa min/max.

## 9. Độ phức tạp và chi phí thực tế

Đặt \(n\) là số bản ghi và \(R=max-min+1\) là kích thước miền khóa (nếu đầu vào không rỗng). Bốn pha có chi phí:

| Pha | Thời gian |
|---|---:|
| Duyệt tìm min/max | \(O(n)\) |
| Khởi tạo và đếm tần suất | \(O(R+n)\) |
| Tính tổng tiền tố | \(O(R)\) |
| Duyệt ngược đặt n bản ghi vào output | \(O(n)\) |
| **Tổng cộng** | **\(O(n+R)\)** |

- Mảng count có **\(R\)** ô số nguyên: \(O(R)\) bộ nhớ phụ.
- Mảng output có **\(n\)** vị trí tham chiếu bản ghi: \(O(n)\) bộ nhớ kết quả.
- Tổng bộ nhớ ngoài đầu vào: **\(O(n+R)\)** nếu tính cả output.
- Thuật toán không sắp xếp tại chỗ (*not in-place*) theo nghĩa thông thường vì cần mảng kết quả riêng.

Nếu \(R=O(n)\), tổng thời gian có thể xem là \(O(n)\). Nếu \(R\) rất lớn so với \(n\), việc tạo mảng count sẽ tốn kém dù số phần tử ít: counting sort có thể thua các thuật toán so sánh \(O(n\log n)\) về cả thời gian lẫn RAM.

Không được phát biểu rằng counting sort luôn chạy \(O(n)\) chỉ dựa vào việc có n bản ghi. Phải ghi **\(O(n+R)\)** và nêu rõ miền khóa. Nếu biết \(R\) là hằng số nhỏ cố định, \(O(n+R)\) mới rút gọn thành \(O(n)\).

### Đếm có thể tràn không?

Với một mảng Java thông thường, \`input.length\` là số nguyên int không âm; tổng tần suất không vượt số phần tử. Do đó các giá trị prefix count của ví dụ không vượt n. Tuy nhiên nếu xử lý một dòng dữ liệu lớn hơn miền chỉ số int, tích lũy số đếm từ nhiều lô, hoặc dùng kiểu dữ liệu khác, cần xác định kiểu số đủ lớn và cả khả năng đánh địa chỉ của cấu trúc kết quả. Đây là vấn đề khác với tràn hiệu max-min khi xác định miền.

## 10. Các trường hợp biên cần thử

| Đầu vào | Điều cần xác nhận |
|---|---|
| Mảng rỗng | Trả mảng rỗng; không truy cập min/max không tồn tại |
| Một bản ghi | Trả một phần tử đúng bản ghi, không dịch vị trí |
| Tất cả cùng khóa | Giữ **nguyên thứ tự các nhãn**; kiểm tra ổn định rõ nhất |
| Khóa lặp xen kẽ | Các nhóm khóa ổn định dù đầu vào bị trộn |
| Khóa âm | Dùng offset \`key-min\` khi truy cập count; kết quả vẫn tăng theo số nguyên |
| Khóa rất xa nhau | Miền R có thể không khả thi về RAM; kiểm tra trước cấp phát |
| Khóa min/max của int | Dùng long để tính độ rộng miền, không để \`max-min+1\` tràn |
| Payload có nhiều thuộc tính | Chuyển **cả bản ghi hoặc đúng tham chiếu**, không chỉ khóa |
| Các bản ghi cùng khóa nhưng khác nhãn | Thứ tự nhãn đầu ra phải bằng thứ tự nhãn ban đầu trong từng nhóm |
| Kết quả cần thứ tự giảm | Phải tính lại biên nhóm theo chiều giảm và chứng minh quy tắc ghi ổn định tương ứng |

Một số phiên bản counting sort chỉ biết miền khóa \([0,K]\) trước, không cần quét tìm min/max. Điều đó không thay đổi bản chất: phải cấp phát mảng đếm độ dài \(K+1\), biến tần suất thành vị trí và đặt bản ghi có chú ý tới thứ tự bằng khóa.

## 11. Ổn định và nhiều lượt sắp xếp theo khóa

Giả sử muốn sắp các bản ghi theo **(lớp tăng, tên tăng)**, có thể:

1. Sắp xếp ổn định theo **tên** (khóa phụ).
2. Sắp xếp ổn định theo **lớp** (khóa chính).

Sau lượt thứ hai, các bản ghi cùng lớp vẫn giữ thứ tự theo tên đã có từ lượt thứ nhất. Nếu lượt sắp theo lớp không ổn định, nó có thể xáo trộn các bản ghi cùng lớp và phá thứ tự theo tên.

Với **radix sort LSD** trên chữ số: sắp xếp ổn định theo chữ số hàng đơn vị, sau đó hàng chục, hàng trăm... Tính ổn định giữ nguyên thứ tự theo các chữ số ít quan trọng hơn trong mỗi nhóm cùng chữ số mới. Nếu một lượt counting sort phân phối chữ số mà duyệt xuôi với con trỏ cuối, các bản ghi có chữ số hiện tại giống nhau có thể bị đảo, khiến kết quả cuối cùng sai mặc dù từng lượt vẫn nhóm đúng chữ số.

**Tính ổn định là thuộc tính của toàn bộ quy trình đặt phần tử**, vì vậy khi dùng counting sort làm bước con trong radix sort, không được thay đổi tùy tiện hướng duyệt hoặc kiểu biên nhóm.

## 12. Sai lầm thường gặp

1. **Cho rằng counting sort tự nhiên ổn định:** đếm tần suất không quyết định thứ tự của bản ghi cùng khóa; pha xây dựng output mới quyết định.
2. **Duyệt trái sang phải nhưng giảm con trỏ cuối:** đảo thứ tự các bản ghi cùng khóa, như A–C–F biến thành F–C–A.
3. **Tính prefix count rồi dùng nó như vị trí 0-based chưa giảm:** \`C[v]\` là biên phải loại trừ; vị trí ghi cuối hợp lệ là \`C[v]-1\`.
4. **Quên cập nhật con trỏ sau mỗi phần tử:** các phần tử cùng khóa sẽ ghi đè cùng một ô.
5. **Không giữ nguyên payload:** sắp xếp bản ghi phải di chuyển **toàn bộ bản ghi**, không chỉ sao chép khóa.
6. **Chỉ kiểm thử dãy số nguyên:** không thấy được sự đảo thứ tự giữa những số bằng nhau; cần dùng nhãn hoặc ID.
7. **Không tính miền khóa R:** thuật toán có thể tiêu thụ RAM khổng lồ hoặc tràn khi tính max-min+1.
8. **Dùng khóa âm trực tiếp làm chỉ số mảng:** sẽ truy cập âm; cần bù offset từ min và kiểm tra miền.
9. **Đánh đồng số đếm gốc với con trỏ sau khi tính prefix:** mảng count đã đổi ý nghĩa và tiếp tục bị giảm trong pha ghi.
10. **Sử dụng một lượt phân phối không ổn định trong radix sort LSD:** phá thứ tự thiết lập từ lượt chữ số trước.
11. **Khẳng định “in-place, O(1) memory” cho phiên bản trả mảng mới:** cần \(O(R)\) mảng count và \(O(n)\) mảng output.
12. **Coi sắp xếp theo khóa tăng là đủ:** nếu hợp đồng còn yêu cầu ổn định thì thứ tự các bản ghi bằng khóa cũng phải được bảo toàn.

## 13. Bài tập tự kiểm tra

**Bài 1.** Đầu vào \`[1:A,2:B,1:C,2:D,1:E]\`. Hãy viết kết quả sắp tăng theo khóa và **ổn định**.

*Đáp án:* \`[1:A,1:C,1:E,2:B,2:D]\`. Những nhãn có khóa 1 giữ A–C–E và khóa 2 giữ B–D.

**Bài 2.** Với tần suất theo khóa 0,1,2 là \`[1,2,3]\`, tổng tiền tố là gì và nhóm khóa 2 nằm ở những chỉ số nào trong mảng 0-based?

*Đáp án:* Tổng tiền tố \`[1,3,6]\`; nhóm khóa 2 nằm ở chỉ số **3,4,5**. Biên phải loại trừ của nhóm là 6.

**Bài 3.** Vì sao đi từ phải sang trái với \`output[--count[v]] = x\` giữ ổn định?

*Đáp án:* Bản ghi cùng khóa xuất hiện muộn hơn được xét trước và nhận **vị trí cuối hơn** trong nhóm. Bản ghi xuất hiện sớm hơn được xét sau, khi con trỏ đã giảm, nên nhận chỉ số đầu ra nhỏ hơn.

**Bài 4.** Có thể duyệt từ trái sang phải mà vẫn ổn định không?

*Đáp án:* Có. Dùng con trỏ **đầu nhóm** \`start[v]\` và đặt tại \`output[start[v]++]\`. Bản ghi đến trước nhận vị trí trước.

**Bài 5.** Một mảng chỉ có hai bản ghi \`[-1:X, 1:Y]\`. Vì sao không nên chỉ lấy \`int range = max-min+1\` trong trường hợp tổng quát với khóa int?

*Đáp án:* Ví dụ nhỏ này không tràn, nhưng với khóa từ **Integer.MIN_VALUE** đến **Integer.MAX_VALUE**, hiệu max-min và kích thước miền vượt giới hạn int. Phải dùng long khi tính và kiểm tra phạm vi có thể cấp phát trước khi ép kiểu.

**Ghi nhớ:** Counting sort ổn định không chỉ “đếm đúng”. Thuật toán phải dành đúng đoạn vị trí cho mỗi khóa và cấp vị trí đúng hướng. **Duyệt ngược + con trỏ cuối giảm** hoặc **duyệt xuôi + con trỏ đầu tăng** đều giữ được thứ tự ban đầu của các bản ghi bằng khóa. Đó là điều kiện quan trọng để dùng counting sort cho bản ghi và làm bước phân phối ổn định trong radix sort LSD.