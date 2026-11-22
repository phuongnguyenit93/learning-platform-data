# Misra–Gries và bước kiểm chứng tần suất

> **Chủ đề:** Computer Science Algorithms → **Trực tuyến và luồng**.  
> **Mục tiêu:** Tìm mọi phần tử xuất hiện **nhiều hơn n/k lần** trong một luồng dài mà lượt đầu chỉ lưu tối đa **k−1 bộ đếm**. Giải thích thuật toán **Misra–Gries**, bất biến triệt tiêu nhóm k phần tử phân biệt, chứng minh **không bỏ sót heavy hitter** nhưng có thể có **ứng viên giả**, cách **đếm lại chính xác ở lượt hai**, sai số của bộ đếm, độ phức tạp, tổng hợp sketch từng phân đoạn, các trường hợp biên và lỗi thường gặp. Có **ba chương trình Java 17 độc lập**, stdout, kiểm thử oracle và bài tập.

## 1. Bài toán: heavy hitters trong dữ liệu dòng chảy

Một luồng phần tử (*stream*) có thứ tự:

`a1, a2, ..., an`.

Mỗi phần tử có thể là mã người dùng, ID sản phẩm, gói tin, sự kiện hệ thống, từ khóa, số nguyên hoặc một khóa bất kỳ có thể so sánh bằng phép bằng nhau.

Định nghĩa tần suất thực:

`f(x)=|{i : ai=x}|`.

Với tham số nguyên `k≥2`, ta cần trả tập:

`H_k={x : f(x)>n/k}`.

Dấu **lớn hơn nghiêm ngặt** rất quan trọng. Nếu n=12 và k=3, các phần tử có tần suất 5 trở lên là heavy hitter; tần suất đúng 4 **không** phải heavy hitter theo định nghĩa này.

**Ví dụ ứng dụng:**

- Giám sát một số ít ID gây lượng truy cập đặc biệt lớn.
- Phát hiện các sự kiện phổ biến trong log mà không giữ toàn bộ histogram.
- Đưa ra danh sách ứng viên khóa thường gặp để đọc lại dữ liệu và tính thống kê chính xác.
- Tổng hợp các phân đoạn dữ liệu trong hệ thống phân tán.

Trong một luồng có nhiều khóa phân biệt, bảng đếm đầy đủ có thể cần O(U) bộ nhớ, với U là số khóa khác nhau. Misra–Gries thay thế bảng đó bằng **O(k) bộ nhớ** bất kể U lớn thế nào.

### 1.1. Không có k phần tử cùng vượt n/k

Giả sử có ít nhất k phần tử khác nhau, mỗi phần tử xuất hiện **hơn n/k** lần. Tổng tần suất của chúng sẽ lớn hơn `k·n/k=n`, vô lý vì luồng chỉ có n vị trí.

Vì vậy:

`|H_k|≤k−1`.

Đó là lý do một phương pháp chỉ giữ k−1 ứng viên có cơ hội tìm được mọi heavy hitter.

### 1.2. Bài toán tìm ứng viên khác đếm chính xác

Hai câu hỏi phải tách riêng:

1. **Ai có thể** có tần suất >n/k?
2. **Ai thực sự** có tần suất >n/k?

Misra–Gries lượt đầu trả lời câu1 một cách xác định và không bỏ sót. Lượt thứ hai đếm tần suất thật của các ứng viên và trả lời câu2. Nếu chỉ có một lượt, bộ đếm MG là **ước lượng dưới**, không phải histogram thực.

## 2. Ba quy tắc của Misra–Gries

Duy trì một ánh xạ `counters` từ khóa tới **số đếm nguyên dương**, chứa nhiều nhất `k−1` khóa.

Khi đọc một phần tử x:

1. **x đã có:** tăng `counters[x]` thêm1.
2. **x chưa có, còn ô trống:** thêm x với bộ đếm1.
3. **x chưa có, đã đủ k−1 khóa:** giảm **tất cả** bộ đếm hiện có đi1; x hiện tại **không được thêm**; xóa mọi bộ đếm trở thành0.

Cả ba trường hợp đều xử lý **đúng một phần tử của luồng**. Không cần quay lại phần tử đã đọc.

Pseudocode:

```text
MisraGries(stream, k):
    require k >= 2
    counters := empty map
    deletedGroups := 0

    for each x in stream:
        if counters contains x:
            counters[x] := counters[x] + 1
        else if size(counters) < k - 1:
            counters[x] := 1
        else:
            for each key y in counters:
                counters[y] := counters[y] - 1
                if counters[y] == 0:
                    remove y
            deletedGroups := deletedGroups + 1

    return counters, deletedGroups
```

**Không thay bước3 bằng “xóa khóa có đếm nhỏ nhất”**: đó là một chính sách khác và không có cùng chứng minh triệt tiêu k khóa. Bước3 phải giảm đồng thời mọi bộ đếm, và **không chèn x** trong vòng đó.

### 2.1. Vì sao chọn k−1 thay vì k bộ đếm?

Khi bảng đầy, có `k−1` khóa khác nhau đang lưu và x là khóa thứ k **khác tất cả khóa đó**. Có thể coi thao tác giảm đồng thời và bỏ x là hủy **một lần xuất hiện của k khóa khác nhau**. Đó là đơn vị cơ bản của chứng minh.

Nếu giữ k bộ đếm, ngưỡng bảo đảm tự nhiên sẽ thay đổi. Không được dùng một cấu trúc k bộ đếm rồi vẫn tuyên bố công thức k−1 mà không phân tích lại.

### 2.2. Bộ đếm không phải số lần xuất hiện thật

Một khóa có thể đã xuất hiện nhiều lần nhưng bị giảm hoặc xóa khỏi bảng. Nếu nó xuất hiện lại, thuật toán có thể thêm nó với bộ đếm1. Vì thế số đếm ở cuối chỉ phản ánh lượng phần tử **chưa bị triệt tiêu** trong cách diễn giải của thuật toán, không ghi lại mọi lần xuất hiện trong lịch sử.

## 3. Bất biến triệt tiêu: căn cứ của bảo đảm

Gọi:

- `N`: số phần tử đã xử lý;
- `C`: tổng các bộ đếm hiện tại, `C=Σ_y counters[y]`;
- `D`: số lần gặp trường hợp3, tức số lần triệt tiêu một nhóm;
- `k`: tham số thuật toán.

**Bất biến chính xác của bản Misra–Gries đơn vị:**

`N = C + k·D`.

### 3.1. Chứng minh bằng quy nạp

Ban đầu N=C=D=0, công thức đúng.

Khi gặp khóa đã có hoặc chèn vào ô trống:

- N tăng1;
- C tăng1;
- D không đổi.

Vì vậy đẳng thức vẫn đúng.

Khi gặp khóa mới lúc bảng đầy:

- N tăng1;
- Có k−1 bộ đếm dương bị giảm đi1 ⇒ C giảm `k−1`;
- D tăng1.

Chênh lệch `N−C` tăng `1+(k−1)=k`, đúng bằng lượng tăng của `kD`.

Tại mọi thời điểm:

`D=(N−C)/k≤floor(N/k)`.

Trong code dùng `long` cho N, C, D khi luồng có thể dài; nếu lưu nguyên luồng trong `int[]`, N của demo không vượt chiều dài mảng Java.

### 3.2. Diễn giải hủy nhóm

Mỗi lần trường hợp3 xảy ra, ta xóa về mặt tư duy một lần xuất hiện của **k khóa khác nhau**:

- k−1 khóa trong bảng bị trừ1;
- phần tử x mới đến bị tiêu thụ và không được chèn.

Sau D lần như vậy, tối đa **D lần xuất hiện của cùng một khóa** có thể bị xóa, vì một nhóm triệt tiêu không chứa một khóa hai lần.

Tập phần tử “còn sống” có số lần xuất hiện của mỗi khóa bằng bộ đếm cuối cùng. Bài học này là phép **diễn giải để chứng minh**, không cần lưu danh sách phần tử bị hủy trong code.

### 3.3. Chặn lỗi từng khóa

Ký hiệu `m(x)` là bộ đếm cuối cùng của x nếu x còn trong bảng; nếu x không có, quy ước `m(x)=0`.

Do chỉ xóa bớt các lần xuất hiện và mỗi khóa bị xóa nhiều nhất D lần:

`m(x) ≤ f(x) ≤ m(x)+D`.

Vì `D≤floor(N/k)`:

`0≤f(x)−m(x)≤floor(N/k)`.

Đây là **bảo đảm xác định** (*deterministic additive error bound*), không phải một ước lượng theo xác suất.

### 3.4. Không bỏ sót phần tử nặng

Giả sử một khóa x có:

`f(x)>N/k`.

Nếu x **không còn** trong bảng, `m(x)=0` nên theo chặn trên:

`f(x)≤D≤N/k`,

mâu thuẫn. Vậy:

`f(x)>N/k ⇒ x có trong counters`.

Misra–Gries có **không âm tính giả** đối với ngưỡng nghiêm ngặt `>N/k`, khi cài đặt đúng và đọc đủ luồng. Nhưng nó **có thể có dương tính giả**.

### 3.5. Vì sao không có chiều đảo?

Công thức chỉ nói **nếu heavy thì chắc chắn là ứng viên**. Một ứng viên có thể xuất hiện rất ít nhưng vẫn nằm trong bảng vì tới gần cuối luồng còn ô trống hoặc các nhóm đã được triệt tiêu.

Do đó:

`x có trong counters` **không suy ra** `f(x)>N/k`.

Muốn xác nhận cần **lượt kiểm chứng tần suất**.

## 4. Ví dụ 20 phần tử với k=3

Luồng:

```text
1, 2, 1, 3, 1, 4, 1, 2, 2, 1,
5, 2, 2, 1, 6, 2, 1, 7, 2, 2
```

Với `k=3`, bảng chỉ chứa **tối đa hai khóa**. Một số bước quan trọng:

| Bước | Phần tử | Thao tác | Bộ đếm sau bước | D |
|---:|---:|---|---|---:|
| 1 | 1 | Thêm1 | `{1:1}` | 0 |
| 2 | 2 | Thêm2 | `{1:1,2:1}` | 0 |
| 3 | 1 | Tăng1 | `{1:2,2:1}` | 0 |
| 4 | 3 | Bảng đầy, triệt tiêu | `{1:1}` | 1 |
| 5 | 1 | Tăng1 | `{1:2}` | 1 |
| 6 | 4 | Thêm4 | `{1:2,4:1}` | 1 |
| 7 | 1 | Tăng1 | `{1:3,4:1}` | 1 |
| 8 | 2 | Bảng đầy, triệt tiêu | `{1:2}` | 2 |
| 9 | 2 | Thêm2 | `{1:2,2:1}` | 2 |
| 10 | 1 | Tăng1 | `{1:3,2:1}` | 2 |
| 11 | 5 | Bảng đầy, triệt tiêu | `{1:2}` | 3 |
| 14 | 1 | Sau các lần tăng ở bước12–14 | `{1:3,2:2}` | 3 |
| 15 | 6 | Bảng đầy, triệt tiêu | `{1:2,2:1}` | 4 |
| 18 | 7 | Bảng đầy, triệt tiêu | `{1:2,2:1}` | 5 |
| 20 | 2 | Tăng2 | `{1:2,2:3}` | 5 |

Kết quả lượt một:

`counters={1:2,2:3}`.

Tổng số đếm `C=2+3=5`; D=5; N=20:

`C+kD=5+3·5=20`.

Tần suất thật khi kiểm lại:

`f(1)=7`, `f(2)=8`.

Ngưỡng:

`N/k=20/3≈6.6667`.

Vậy cả 1 và 2 đều là heavy hitters, vì 7 và 8 **lớn hơn** 20/3.

Chặn lỗi:

- x=1: `m(1)=2`, `2≤f(1)=7≤2+5=7`.
- x=2: `m(2)=3`, `3≤f(2)=8≤3+5=8`.

Ví dụ cho thấy bộ đếm lượt một **thấp hơn tần suất thật rất nhiều** nhưng vẫn xác định đúng **danh sách có thể cần kiểm lại**.

### 4.1. Nếu x bị xóa khỏi bảng thì sao?

Một khóa x không có trong cuối bảng có `m(x)=0`, nên:

`f(x)≤D=5`.

Vì ngưỡng heavy hitter là `>20/3`, mọi khóa không có trong bảng chắc chắn không heavy. Đây là lý do chỉ cần kiểm lại tối đa k−1 ứng viên.

## 5. Dương tính giả: không được bỏ qua bước kiểm chứng

Với `k=3`, xem luồng:

`1,2,3,4,5,6,7,8,9,10,11`.

N=11, mỗi khóa chỉ xuất hiện **một lần**. Không có heavy hitter vì:

`1≤11/3≈3.667`.

Nhưng Misra–Gries lượt một:

- Hủy các nhóm `{1,2,3}`, `{4,5,6}`, `{7,8,9}`;
- Hai phần tử cuối được thêm vào các ô trống.

Cuối cùng:

`counters={10:1,11:1}`,

với D=3 và `C+kD=2+3·3=11`.

**Cả hai ứng viên đều là dương tính giả**. Lượt hai đo tần suất thật của 10 và11 bằng1 rồi loại cả hai; đầu ra heavy hitter đúng là tập rỗng.

### 5.1. Biên bằng đúng N/k

Với `k=3` và:

`1,2,3,1,2,3`,

N=6, mỗi khóa xuất hiện **đúng hai lần**:

`f(x)=2=N/k`.

Không có khóa nào thuộc `H_3`, vì đề yêu cầu **>`** chứ không phải **≥**. Misra–Gries có thể trả bảng rỗng, điều đó **không vi phạm** bất kỳ bảo đảm nào.

### 5.2. Vì sao không dùng m(x)>N/k làm bộ lọc?

Trong ví dụ N=20, m(1)=2 và m(2)=3, đều nhỏ hơn6.667 dù tần suất thật của hai khóa đều vượt ngưỡng. Lọc bằng **bộ đếm MG** ở bước này có thể loại nhầm heavy hitters. Chỉ lọc sau khi có **exact counts ở lượt hai**.

### 5.3. Trường hợp không có heavy hitter

Thuật toán không bắt buộc trả về ít nhất một khóa. Một luồng gần đồng đều có thể không có phần tử nào vượt N/k; kết quả chính xác phải là **tập rỗng**.

## 6. Lượt hai: kiểm chứng tần suất chính xác

Sau lượt một, bảng chứa ≤k−1 khóa ứng viên. Ta tạo bảng `exactCounts` khởi tạo bằng0 **chỉ cho các khóa này**, rồi đọc lại toàn bộ luồng:

```text
candidates := keys(MisraGries(stream, k).counters)
exactCounts := map(candidate -> 0)

for each x in the replayed stream:
    if x is in exactCounts:
        exactCounts[x] := exactCounts[x] + 1

heavyHitters := {
    (x, exactCounts[x])
    for x in candidates
    if exactCounts[x] > n / k
}
```

Lượt hai trả:

- **Đúng tập** phần tử có tần suất `>n/k`.
- **Đúng tần suất** của những phần tử được trả.
- Không cần bảng đếm cho toàn bộ U khóa.

### 6.1. Chứng minh đầu ra exact

**Không bỏ sót:** Mọi heavy hitter đã được chứng minh nằm trong danh sách ứng viên từ lượt một. Lượt hai đếm đúng tất cả lần xuất hiện của ứng viên, nên mọi heavy hitter vượt threshold và được giữ.

**Không giữ sai:** Mỗi ứng viên được giữ chỉ khi tần suất thật đo ở lượt hai `>n/k`. Do đó không còn dương tính giả.

Kết hợp hai chiều suy ra tập kết quả **chính xác**.

### 6.2. Cần nguồn có thể đọc lại

Nếu đầu vào là file log hoặc bảng dữ liệu có thể quét lại, chi phí thêm một lượt thường chấp nhận được.

Nếu đầu vào là luồng chỉ đi qua **một lần và không được lưu/replay**, không thể tự gọi một biến `exactCount` từ bộ đếm MG là “đúng”. Cần cơ chế khác: lưu sự kiện, pipeline có log đọc lại, một pass thứ hai theo batch, hoặc chấp nhận kết quả xấp xỉ và khoảng lỗi.

### 6.3. Không được xác minh trên dữ liệu khác

Hai lượt phải kiểm **cùng một multiset sự kiện** của một phiên snapshot:

- Nếu log có sự kiện thêm/xóa giữa hai lượt, N, candidate và exact frequency có thể không tương ứng.
- Cần checkpoint/snapshot, offset bắt đầu–kết thúc hoặc một ranh giới batch xác định.
- Nếu sắp thứ tự lại nhưng **không thêm/bớt** sự kiện, exact frequency không đổi; bộ đếm MG và danh sách ứng viên **có thể đổi**, nhưng bảo đảm không bỏ sót vẫn giữ.

### 6.4. Cộng dồn exact counts

Với Java `int[]` demo, mỗi khóa có frequency ≤số phần tử mảng; vẫn dùng `long` để minh họa API đếm luồng dài. Trên hệ thống thực, tránh tràn counter và đảm bảo so sánh ngưỡng dùng số nguyên chính xác, không dựa vào phép chia floating nếu không cần.

## 7. Java 17 — hai lượt Misra–Gries đầy đủ

Lưu **MisraGriesTwoPassDemo.java**:

```java
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;

public class MisraGriesTwoPassDemo {
    record Summary(int k, long length, long cancellations,
                   TreeMap<Integer, Long> counters) {}

    static Summary firstPass(int[] stream, int k) {
        if (stream == null || k < 2) {
            throw new IllegalArgumentException("k must be >= 2");
        }
        TreeMap<Integer, Long> counters = new TreeMap<>();
        long deletedGroups = 0;

        for (int x : stream) {
            if (counters.containsKey(x)) {
                counters.put(x, counters.get(x) + 1);
            } else if (counters.size() < k - 1) {
                counters.put(x, 1L);
            } else {
                Iterator<Map.Entry<Integer, Long>> it =
                        counters.entrySet().iterator();
                while (it.hasNext()) {
                    Map.Entry<Integer, Long> item = it.next();
                    long updated = item.getValue() - 1;
                    if (updated == 0) it.remove();
                    else item.setValue(updated);
                }
                deletedGroups++;
            }
        }
        return new Summary(k, stream.length, deletedGroups, counters);
    }

    static TreeMap<Integer, Long> exactCandidateCounts(
            int[] stream, Summary summary) {
        TreeMap<Integer, Long> exact = new TreeMap<>();
        for (int key : summary.counters().keySet()) {
            exact.put(key, 0L);
        }
        for (int x : stream) {
            if (exact.containsKey(x)) {
                exact.put(x, exact.get(x) + 1);
            }
        }
        return exact;
    }

    static TreeMap<Integer, Long> verifiedHeavyHitters(
            int[] stream, Summary summary) {
        TreeMap<Integer, Long> exact =
                exactCandidateCounts(stream, summary);
        long threshold = summary.length() / summary.k();
        exact.entrySet().removeIf(e -> e.getValue() <= threshold);
        return exact;
    }

    static boolean massInvariant(Summary summary) {
        long stored = 0;
        for (long count : summary.counters().values()) stored += count;
        return summary.length()
                == stored + (long) summary.k() * summary.cancellations();
    }

    public static void main(String[] args) {
        int[] stream = {
            1, 2, 1, 3, 1, 4, 1, 2, 2, 1,
            5, 2, 2, 1, 6, 2, 1, 7, 2, 2
        };
        Summary s = firstPass(stream, 3);

        System.out.println("length=" + s.length() + ", k=" + s.k());
        System.out.println("first pass counters=" + s.counters());
        System.out.println("cancellations=" + s.cancellations());
        System.out.println("mass invariant=" + massInvariant(s));
        System.out.println("exact candidate counts="
                + exactCandidateCounts(stream, s));
        System.out.println("verified heavy hitters="
                + verifiedHeavyHitters(stream, s));

        int[] allDistinct = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
        Summary falsePositive = firstPass(allDistinct, 3);
        System.out.println("false-positive candidates="
                + falsePositive.counters());
        System.out.println("false-positive verified="
                + verifiedHeavyHitters(allDistinct, falsePositive));

        int[] boundary = {1, 2, 3, 1, 2, 3};
        System.out.println("strict threshold boundary="
                + verifiedHeavyHitters(boundary, firstPass(boundary, 3)));
        System.out.println("empty stream candidates="
                + firstPass(new int[0], 3).counters());

        boolean invalidKRejected = false;
        try {
            firstPass(stream, 1);
        } catch (IllegalArgumentException ex) {
            invalidKRejected = true;
        }
        System.out.println("invalid k rejected=" + invalidKRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MisraGriesTwoPassDemo.java
java MisraGriesTwoPassDemo
```

Stdout dự kiến:

```text
length=20, k=3
first pass counters={1=2, 2=3}
cancellations=5
mass invariant=true
exact candidate counts={1=7, 2=8}
verified heavy hitters={1=7, 2=8}
false-positive candidates={10=1, 11=1}
false-positive verified={}
strict threshold boundary={}
empty stream candidates={}
invalid k rejected=true
```

### 7.1. Vì sao dùng TreeMap?

Ví dụ in ra theo thứ tự tăng dần của ID để stdout ổn định trên các lần chạy. Thuật toán MG chỉ cần ánh xạ khóa→số đếm; trong production có thể dùng HashMap để có truy cập trung bình O(1), nhưng cần chú ý chi phí duyệt mọi counter ở bước triệt tiêu.

### 7.2. Công thức ngưỡng trong code

Đếm chính xác `f(x)` là số nguyên. Điều kiện:

`f(x)>N/k`,

tương đương:

`f(x)>floor(N/k)`.

Java `long threshold=N/k` dùng chia nguyên khi N≥0, k≥2, vì vậy lọc `count>threshold` đúng với định nghĩa nghiêm ngặt.

### 7.3. Không lấy N từ số lượng counter

N là **số phần tử luồng gốc**, không phải tổng bộ đếm còn lại và không phải số khóa phân biệt. Trong ví dụ N=20 trong khi tổng counter chỉ bằng5.

## 8. Các trường hợp biên của thuật toán

### 8.1. k=2: đa số tuyệt đối

Với k=2, chỉ giữ một counter. MG trở thành biến thể của thuật toán majority vote kiểu Boyer–Moore để **tìm ứng viên** phần tử xuất hiện >N/2.

Ví dụ:

`9,2,9,3,9,9,5`.

N=7, khóa9 xuất hiện4 lần (>3.5). Lượt một giữ ứng viên9, nhưng lượt hai vẫn cần đếm **đúng4** để xác minh majority.

Một ứng viên majority không có nghĩa dữ liệu thực sự có đa số; nếu không có khóa nào xuất hiện >N/2, vẫn có thể còn một ứng viên sau lượt đầu.

### 8.2. k>N

Khi k>N, bảng có ít nhất N ô khả dụng, nên sẽ không có lần triệt tiêu nào, D=0. Mọi khóa xuất hiện được lưu cùng **tần suất chính xác**.

Vì `N/k<1`, mọi khóa đã xuất hiện ít nhất1 lần đều đạt điều kiện `f(x)>N/k`. Lượt hai không cần thiết về mặt toán học trong trường hợp này, nhưng API hai lượt vẫn cho đúng kết quả.

### 8.3. N=0

Luồng rỗng không có heavy hitter. D=0, counters rỗng, kết quả lượt hai rỗng. Không được chia cho N để tính tỷ lệ tần suất rồi gây lỗi chia0.

### 8.4. k không hợp lệ

Bản cài đặt chuẩn ở đây quy định k≥2. `k=1` sẽ tạo ngân sách0 counter và ngưỡng >N; bài toán không có heavy hitter, nhưng không tương thích với nhánh thao tác bảng đầy thông thường. Nên từ chối `k<2` thay vì âm thầm thay ngữ nghĩa.

### 8.5. Khóa âm, số0 và chuỗi

MG không yêu cầu khóa dương hoặc phải là số. Các số âm, số0, chuỗi và ID tùy ý đều hợp lệ, miễn phép bằng nhau và lưu khóa có hành vi nhất quán. `null` có cần hỗ trợ không là quyết định của cấu trúc map và hợp đồng API.

### 8.6. Dữ liệu rất lệch hoặc mọi khóa khác nhau

Một phần tử rất thường gặp sẽ không bị loại khỏi cuối bảng nếu f>N/k. Ngược lại, nếu mọi khóa khác nhau, kết quả exact thường rỗng, nhưng bảng lượt một có thể còn tối đa k−1 khóa cuối — ứng viên giả.

## 9. Độ phức tạp thời gian và bộ nhớ

Gọi N là số phần tử luồng và k≥2.

**Bộ nhớ:** tối đa k−1 khóa/counter, O(k) mục lưu trữ. Bảng second-pass cũng O(k). Nếu khóa là chuỗi có độ dài thay đổi, cần tính thêm bộ nhớ lưu **bản thân khóa**, không chỉ số lượng counter.

**Thời gian khi dùng HashMap:** bước tăng/chèn thường O(1) kỳ vọng; khi bảng đầy và khóa mới, giảm tất cả k−1 bộ đếm mất O(k). Nhưng mỗi lần triệt tiêu cần k phần tử đóng góp theo bất biến `D≤N/k`, nên tổng chi phí của **mọi vòng giảm** là O(kD)=O(N). Vì vậy có thể phân tích **amortized O(N) expected** cho hashing phù hợp và counter update đơn vị.

**Thời gian với TreeMap ở Java demo:** mỗi tìm/chèn/xóa có chi phí O(log k), vòng quét O(k) ở từng lần hủy. Tổng O(N log k+N) thao tác thông thường dưới giả thiết phép so sánh khóa O(1). Không được gọi `O(1)` worst-case cho từng sự kiện vì sự kiện triệt tiêu có thể quét toàn bảng.

**Lượt hai:** O(N) tra cứu kỳ vọng với HashMap, hoặc O(N log k) với TreeMap; thêm O(k) để lọc. Nếu phải đọc dữ liệu từ ổ đĩa, thông lượng I/O hai lượt có thể là chi phí chi phối.

### 9.1. Hai lượt không có nghĩa bộ nhớ chứa toàn bộ luồng

Một implementation streaming thực sự quét một file hoặc nguồn replayable, không cần đưa mọi sự kiện vào một mảng. Các demo Java dùng `int[]` để tái lập stdout và tạo oracle; phần **thuật toán** chỉ giữ O(k) bộ nhớ, nhưng **bản demo nếu tính cả mảng input** tất nhiên chiếm O(N).

### 9.2. Nếu k rất lớn

Khi k gần N, bảng có thể lưu nhiều khóa, tiến gần histogram. Chọn k là một trade-off giữa bộ nhớ và ngưỡng phát hiện; không có giá trị k “đúng cho mọi ứng dụng”.

### 9.3. Chi phí khóa không phải số nguyên

Với khóa chuỗi dài, băm/so sánh có thể phụ thuộc độ dài khóa; giữ các khóa trong map cần cấp phát và có rủi ro rác/GC. Bảo đảm thuật toán về **số lượng counter** không tự chứng minh thời gian xử lý chuỗi là O(1).

## 10. Dùng tham số k để đặt ngưỡng cần tìm

Từ guarantee:

`f(x)>N/k ⇒ x là ứng viên`.

Muốn tìm mọi khóa chiếm **hơn tỷ lệ φ** của luồng, với 0<φ<1, chọn k sao cho:

`1/k≤φ`.

Một lựa chọn an toàn là `k=ceil(1/φ)` (và ít nhất2). Khi `f(x)>φN`, ta có `f(x)>N/k`, nên MG không bỏ sót.

### 10.1. Khi yêu cầu ≥ thay vì >

Nếu đề muốn các khóa có:

`f(x)≥φN`,

trường hợp đúng bằng ngưỡng có thể bị loại khi `1/k=φ`. Có thể chọn k lớn hơn để `1/k<φ`, hoặc diễn đạt chính xác ngưỡng số nguyên `T` và đảm bảo:

`T>N/k`.

Bộ lọc second-pass phải dùng **điều kiện mà ứng dụng thực sự cần**, không mặc định luôn `>N/k` nếu mục tiêu đã đổi.

### 10.2. Biết n trước hay không?

MG không cần biết N trước khi chạy lượt một. Chỉ tăng `N` mỗi phần tử. Cuối luồng mới dùng N để định ngưỡng và bộ lọc.

Nếu nguồn đang chạy vô hạn và chưa có ranh giới, câu hỏi “tần suất >N/k” cần định nghĩa N theo một epoch, batch, prefix, hay cửa sổ cụ thể.

### 10.3. Mức tin cậy: deterministic không phải probability

Misra–Gries không cần seed ngẫu nhiên, không cần hash ngẫu nhiên để chứng minh không bỏ sót. Kết quả counters phụ thuộc thứ tự, nhưng bảo đảm inclusion đúng trên **mọi thứ tự** của cùng multiset.

## 11. Gộp các phân đoạn: Misra–Gries có thể tạo sketch hợp nhất

Trong hệ thống phân tán, luồng thường được chia thành các phần liên tiếp hoặc partition rời nhau:

`S=S_A ⧺ S_B`.

Mỗi worker có thể chạy MG với **cùng k** rồi gửi sketch gồm:

- Danh sách `(key, counter)` tối đa k−1 phần tử.
- Số sự kiện phần đó `N_A` hay `N_B`.
- Ngân sách sai số `D_A` hay `D_B`.

Để tạo một sketch cho toàn bộ:

1. Cộng counter cùng khóa từ cả hai bảng.
2. Nếu số khóa còn lại **≥k**, chọn `δ` là giá trị counter dương nhỏ nhất đang có.
3. Trừ δ khỏi **tất cả khóa đang có** và xóa các khóa về0.
4. Cộng δ vào ngân sách triệt tiêu D.
5. Lặp đến khi chỉ còn tối đa k−1 khóa.

**Chú ý:** Với phiên bản merge này, có thể giảm đồng thời **m≥k khóa** thay vì đúng k khóa; không nhất thiết còn đẳng thức `N=C+kD`. Tuy nhiên các bound xác định vẫn đúng.

### 11.1. Vì sao gộp không bỏ sót heavy hitter?

Sketch của mỗi phần có:

`m_A(x)≤f_A(x)≤m_A(x)+D_A`,

`m_B(x)≤f_B(x)≤m_B(x)+D_B`.

Sau cộng hai map:

`m_A(x)+m_B(x) ≤ f_A(x)+f_B(x) ≤ m_A(x)+m_B(x)+D_A+D_B`.

Mỗi phép trừ δ trên một nhóm có m≥k khóa phân biệt làm giảm counter của **mỗi khóa** không quá δ, trong khi làm giảm **tổng counter** ít nhất `kδ`. Tăng ngân sách D thêm δ giữ:

`m(x)≤f(x)≤m(x)+D`,

và luôn có:

`kD≤N`.

Do đó mọi khóa với `f(x)>N/k` vẫn phải xuất hiện trong sketch hợp nhất. Đây là lý do merge đúng có thể dùng để chọn **ứng viên toàn cục**.

### 11.2. Đẳng thức N=C+kD đổi thành bất đẳng thức

Ở sketch tạo bởi MG đơn vị:

`N=C+kD`.

Sau merge có thể chỉ bảo đảm:

`C+kD≤N`

vì một lần giảm δ từ m>k khóa xóa **mδ** đơn vị counter, lớn hơn kδ. Không dùng test equality của bản single-stream để bác bỏ một sketch merge hợp lệ.

### 11.3. Kết quả merge không cần bằng kết quả chạy tuần tự

Chạy MG một lượt trên `S_A ⧺ S_B` và gộp hai sketch có thể cho **counters khác nhau**. Hai kết quả đều có thể hợp lệ nếu giữ đúng cận lỗi và không bỏ sót heavy hitter.

Không đặt test `mergedCounters.equals(directCounters)` làm điều kiện correctness chung. Test đúng là:

- Số khóa ≤k−1.
- `kD≤N`.
- Với mọi khóa: `m(x)≤f(x)≤m(x)+D`.
- Mọi khóa thật có `f(x)>N/k` còn trong bảng.
- Sau lượt kiểm chứng toàn cục, tập heavy hitters là **như nhau**.

### 11.4. Cần đúng phân vùng và nguồn replay

Nếu hai worker xử lý các vùng **chồng lặp** mà không loại trùng sự kiện, tổng N và frequency bị đếm hai lần. Nếu hai vùng bị bỏ sót sự kiện, kết quả không còn tương ứng luồng gốc. Việc merge sketch không sửa được lỗi partitioning hay snapshot.

### 11.5. Gộp nhiều partition

Có thể áp dụng merge theo cây. Mỗi nút nội bộ nhận sketch `(N,D,counters)` từ hai con rồi tạo sketch mới. Vì mỗi bước giữ bound, toàn cây vẫn có guarantee, với cùng k và dữ liệu không bị đếm trùng. Second pass cần đếm lại ứng viên trên **toàn bộ các partition** và cộng exact counts.

## 12. Java 17 — gộp sketch và kiểm chứng toàn cục

Lưu **MisraGriesMergeDemo.java**:

```java
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;

public class MisraGriesMergeDemo {
    record Summary(int k, long n, long budget,
                   TreeMap<Integer, Long> counters) {}

    static Summary sketch(int[] stream, int k) {
        if (stream == null || k < 2) {
            throw new IllegalArgumentException("Invalid input");
        }
        TreeMap<Integer, Long> c = new TreeMap<>();
        long d = 0;

        for (int x : stream) {
            if (c.containsKey(x)) {
                c.put(x, c.get(x) + 1);
            } else if (c.size() < k - 1) {
                c.put(x, 1L);
            } else {
                Iterator<Map.Entry<Integer, Long>> it =
                        c.entrySet().iterator();
                while (it.hasNext()) {
                    Map.Entry<Integer, Long> e = it.next();
                    long next = e.getValue() - 1;
                    if (next == 0) it.remove();
                    else e.setValue(next);
                }
                d++;
            }
        }
        return new Summary(k, stream.length, d, c);
    }

    static Summary merge(Summary a, Summary b) {
        if (a.k() != b.k()) {
            throw new IllegalArgumentException("Different k");
        }

        TreeMap<Integer, Long> c = new TreeMap<>(a.counters());
        for (Map.Entry<Integer, Long> e : b.counters().entrySet()) {
            c.merge(e.getKey(), e.getValue(), Long::sum);
        }
        long budget = a.budget() + b.budget();

        while (c.size() >= a.k()) {
            long minimum = Long.MAX_VALUE;
            for (long count : c.values()) {
                minimum = Math.min(minimum, count);
            }

            Iterator<Map.Entry<Integer, Long>> it =
                    c.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<Integer, Long> e = it.next();
                long next = e.getValue() - minimum;
                if (next == 0) it.remove();
                else e.setValue(next);
            }
            budget += minimum;
        }
        return new Summary(a.k(), a.n() + b.n(), budget, c);
    }

    static TreeMap<Integer, Long> verify(
            int[] replay, Summary s) {
        TreeMap<Integer, Long> exact = new TreeMap<>();
        for (int x : s.counters().keySet()) exact.put(x, 0L);
        for (int x : replay) {
            if (exact.containsKey(x)) {
                exact.put(x, exact.get(x) + 1);
            }
        }
        exact.entrySet().removeIf(
                e -> e.getValue() <= s.n() / s.k());
        return exact;
    }

    static boolean boundsHold(int[] all, Summary s) {
        TreeMap<Integer, Long> truth = new TreeMap<>();
        for (int x : all) truth.merge(x, 1L, Long::sum);

        long sum = 0;
        for (long count : s.counters().values()) sum += count;
        if (s.counters().size() >= s.k()
                || sum + (long) s.k() * s.budget() > s.n()) {
            return false;
        }
        for (Map.Entry<Integer, Long> e : truth.entrySet()) {
            long estimate = s.counters()
                    .getOrDefault(e.getKey(), 0L);
            if (estimate > e.getValue()
                    || e.getValue() > estimate + s.budget()) {
                return false;
            }
        }
        return true;
    }

    static int[] concat(int[] a, int[] b) {
        int[] all = new int[a.length + b.length];
        System.arraycopy(a, 0, all, 0, a.length);
        System.arraycopy(b, 0, all, a.length, b.length);
        return all;
    }

    public static void main(String[] args) {
        int[] left = {1, 2, 1, 3, 1, 2, 1, 4, 1, 2};
        int[] right = {2, 2, 5, 1, 2, 2, 1, 6, 2, 2};
        int[] all = concat(left, right);

        Summary a = sketch(left, 3);
        Summary b = sketch(right, 3);
        Summary merged = merge(a, b);
        Summary direct = sketch(all, 3);

        System.out.println("left counters=" + a.counters());
        System.out.println("right counters=" + b.counters());
        System.out.println("merged counters=" + merged.counters());
        System.out.println("merged error budget=" + merged.budget());
        System.out.println("merged exact heavy=" + verify(all, merged));
        System.out.println("direct exact heavy=" + verify(all, direct));
        System.out.println("merged bounds hold=" + boundsHold(all, merged));

        int[] p = {1, 1, 2, 2};
        int[] q = {3, 3, 4, 4};
        Summary pruned = merge(sketch(p, 3), sketch(q, 3));
        System.out.println("pruned merged counters=" + pruned.counters());
        System.out.println("pruned merge budget=" + pruned.budget());
        System.out.println("pruned heavy="
                + verify(concat(p, q), pruned));

        boolean mismatchRejected = false;
        try {
            merge(a, sketch(right, 4));
        } catch (IllegalArgumentException ex) {
            mismatchRejected = true;
        }
        System.out.println("different k rejected=" + mismatchRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MisraGriesMergeDemo.java
java MisraGriesMergeDemo
```

Stdout dự kiến:

```text
left counters={1=3, 2=1}
right counters={2=4}
merged counters={1=3, 2=5}
merged error budget=4
merged exact heavy={1=7, 2=9}
direct exact heavy={1=7, 2=9}
merged bounds hold=true
pruned merged counters={}
pruned merge budget=2
pruned heavy={}
different k rejected=true
```

### 12.1. Ví dụ reduction khi union có bốn khóa

Sketch đầu giữ `{1:2,2:2}`, sketch sau `{3:2,4:2}`; hợp nhất có bốn khóa khi k=3. Lấy min=2 và trừ cả bốn khóa, bảng về rỗng; ngân sách D tăng2.

Trên tổng luồng8 phần tử, mỗi khóa xuất hiện2 lần. Ngưỡng `8/3≈2.667`, nên thật sự **không có heavy hitter**. Sketch rỗng và ngân sách2 là hợp lệ: `f(x)=2≤D`.

Ở đây `N=8`, `C=0`, `kD=3·2=6`, nên `C+kD=6<8`; đây là lý do phải dùng **bất đẳng thức** cho sketch merge, không dùng bất biến equality từ MG đơn vị.

### 12.2. Những điều demo không hứa

Phép merge chỉ áp dụng cho cùng k và các phần dữ liệu **không trùng lặp**. Nếu dùng `long` với khối lượng lớn hơn khả năng biểu diễn, cần kiểm overflow hoặc dùng số nguyên lớn. Code minh họa là triển khai didactic, không phải hệ thống streaming production có kiểm tra metadata partition, giao dịch snapshot hay deduplication.

## 13. Kiểm thử độc lập: so với histogram thật trên luồng nhỏ

Một cách test mạnh cho MG là tự tạo luồng có thể liệt kê hoàn toàn rồi dựng histogram `truth`. Không sử dụng chính counters MG làm oracle.

Với mỗi luồng kiểm:

1. `counters.size()≤k−1`.
2. Mọi counter còn lại dương.
3. Với MG trực tiếp: `N=sumCounters+kD`.
4. Với merge: `sumCounters+kD≤N`.
5. Với từng khóa thật x: `m(x)≤f(x)≤m(x)+D`.
6. Nếu `f(x)>N/k` thì x nhất định có trong bảng.
7. Sau recount, tập heavy hitters **bằng đúng** histogram lọc `f(x)>N/k`.
8. Thử cả các luồng không có heavy hitter, k=2, k>N, N=0, khóa âm, các luồng có phần tử phổ biến nằm ở đầu/giữa/cuối, và thứ tự tráo ngẫu nhiên.
9. Với merge, thử điểm chia luồng bằng0 và bằngN, nhiều phân đoạn không giao nhau.
10. Với dữ liệu bất biến, so kết quả exact giữa direct và merged — dù counters có thể khác.

Một test chỉ xác nhận “bộ đếm nhỏ hơn N” là rất yếu; nó không kiểm soundness, completeness hay lỗi ở bước xác minh lượt hai.

## 14. Java 17 — bộ kiểm chứng ngẫu nhiên có oracle

Chương trình sau sinh **2.500 luồng xác định bằng seed**, mỗi luồng có N từ0 tới74, k từ2 tới10, khóa âm/dương và khóa xuất hiện lệch. Với mỗi luồng, nó dựng **histogram chính xác** rồi đối chiếu với:

- MG trực tiếp.
- MG của hai phần và phép merge.
- Recount của ứng viên trong toàn bộ luồng.
- Mọi cận sai số và ngưỡng nghiêm ngặt.

Lưu **MisraGriesOracleDemo.java**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;

public class MisraGriesOracleDemo {
    record Sketch(int k, long n, long budget,
                  TreeMap<Integer, Long> counts) {}

    static Sketch direct(int[] input, int k) {
        if (input == null || k < 2) {
            throw new IllegalArgumentException("Invalid input");
        }
        TreeMap<Integer, Long> counts = new TreeMap<>();
        long d = 0;

        for (int x : input) {
            if (counts.containsKey(x)) {
                counts.put(x, counts.get(x) + 1);
            } else if (counts.size() < k - 1) {
                counts.put(x, 1L);
            } else {
                Iterator<Map.Entry<Integer, Long>> it =
                        counts.entrySet().iterator();
                while (it.hasNext()) {
                    Map.Entry<Integer, Long> e = it.next();
                    long next = e.getValue() - 1;
                    if (next == 0) it.remove();
                    else e.setValue(next);
                }
                d++;
            }
        }
        return new Sketch(k, input.length, d, counts);
    }

    static Sketch merge(Sketch a, Sketch b) {
        if (a.k() != b.k()) {
            throw new IllegalArgumentException("Different k");
        }
        TreeMap<Integer, Long> counts = new TreeMap<>(a.counts());
        for (Map.Entry<Integer, Long> e : b.counts().entrySet()) {
            counts.merge(e.getKey(), e.getValue(), Long::sum);
        }
        long d = a.budget() + b.budget();

        while (counts.size() >= a.k()) {
            long min = Long.MAX_VALUE;
            for (long v : counts.values()) min = Math.min(min, v);

            Iterator<Map.Entry<Integer, Long>> it =
                    counts.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<Integer, Long> e = it.next();
                long next = e.getValue() - min;
                if (next == 0) it.remove();
                else e.setValue(next);
            }
            d += min;
        }
        return new Sketch(a.k(), a.n() + b.n(), d, counts);
    }

    static TreeMap<Integer, Long> histogram(int[] input) {
        TreeMap<Integer, Long> truth = new TreeMap<>();
        for (int x : input) truth.merge(x, 1L, Long::sum);
        return truth;
    }

    static TreeMap<Integer, Long> expectedHeavy(
            TreeMap<Integer, Long> truth, int n, int k) {
        TreeMap<Integer, Long> hits = new TreeMap<>();
        for (Map.Entry<Integer, Long> e : truth.entrySet()) {
            if (e.getValue() > n / k) {
                hits.put(e.getKey(), e.getValue());
            }
        }
        return hits;
    }

    static TreeMap<Integer, Long> replayHeavy(
            int[] input, Sketch sketch) {
        TreeMap<Integer, Long> exactCandidates = new TreeMap<>();
        for (int key : sketch.counts().keySet()) {
            exactCandidates.put(key, 0L);
        }
        for (int x : input) {
            if (exactCandidates.containsKey(x)) {
                exactCandidates.put(x, exactCandidates.get(x) + 1);
            }
        }
        exactCandidates.entrySet().removeIf(
                e -> e.getValue() <= sketch.n() / sketch.k());
        return exactCandidates;
    }

    static void check(int[] input, Sketch sketch,
                      boolean shouldHaveEquality) {
        if (sketch.counts().size() >= sketch.k()
                || sketch.n() != input.length) {
            throw new AssertionError("Sketch shape/length");
        }

        long mass = 0;
        for (long value : sketch.counts().values()) {
            if (value <= 0) throw new AssertionError("Nonpositive count");
            mass += value;
        }
        long represented = mass + (long) sketch.k() * sketch.budget();
        if (represented > sketch.n()) {
            throw new AssertionError("Invalid error budget");
        }
        if (shouldHaveEquality && represented != sketch.n()) {
            throw new AssertionError("Direct mass invariant");
        }

        TreeMap<Integer, Long> truth = histogram(input);
        for (Map.Entry<Integer, Long> e : truth.entrySet()) {
            long estimate = sketch.counts()
                    .getOrDefault(e.getKey(), 0L);
            long exact = e.getValue();
            if (estimate > exact
                    || exact > estimate + sketch.budget()) {
                throw new AssertionError("Frequency error bound");
            }
            if (exact > input.length / sketch.k()
                    && !sketch.counts().containsKey(e.getKey())) {
                throw new AssertionError("Missed heavy hitter");
            }
        }

        if (!replayHeavy(input, sketch).equals(
                expectedHeavy(truth, input.length, sketch.k()))) {
            throw new AssertionError("Wrong verified hitters");
        }
    }

    public static void main(String[] args) {
        Random random = new Random(4902026L);
        final int tests = 2500;

        for (int t = 0; t < tests; t++) {
            int n = random.nextInt(75);
            int k = 2 + random.nextInt(9);
            int[] input = new int[n];

            for (int i = 0; i < n; i++) {
                // Some streams have a strongly repeated key.
                input[i] = random.nextInt(5) == 0
                        ? 42 : random.nextInt(31) - 15;
            }

            Sketch one = direct(input, k);
            check(input, one, true);

            int cut = random.nextInt(n + 1);
            int[] left = Arrays.copyOfRange(input, 0, cut);
            int[] right = Arrays.copyOfRange(input, cut, n);
            Sketch combined = merge(direct(left, k), direct(right, k));
            check(input, combined, false);
        }

        int[] noisy = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
        Sketch spurious = direct(noisy, 3);
        if (spurious.counts().isEmpty()
                || !replayHeavy(noisy, spurious).isEmpty()) {
            throw new AssertionError("False-positive example");
        }

        int[] boundary = {1, 2, 3, 1, 2, 3};
        if (!replayHeavy(boundary, direct(boundary, 3)).isEmpty()) {
            throw new AssertionError("Strict threshold");
        }

        int[] tiny = {7, 8, 7};
        if (direct(tiny, 9).budget() != 0) {
            throw new AssertionError("k > n");
        }

        System.out.println("random cases passed=" + tests);
        System.out.println("direct bounds passed=true");
        System.out.println("merge bounds passed=true");
        System.out.println("verified frequencies passed=true");
        System.out.println("false-positive example passed=true");
        System.out.println("strict boundary passed=true");
        System.out.println("k greater than n passed=true");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MisraGriesOracleDemo.java
java MisraGriesOracleDemo
```

Stdout khi mọi bất biến đều được thỏa:

```text
random cases passed=2500
direct bounds passed=true
merge bounds passed=true
verified frequencies passed=true
false-positive example passed=true
strict boundary passed=true
k greater than n passed=true
```

Nếu một phép kiểm phát hiện phản ví dụ, chương trình ném `AssertionError` thay vì in các dòng `passed=true`.

### 14.1. Test chống implementation bug, không thay định lý

Kiểm 2.500 luồng nhỏ không thể chứng minh algorithm đúng với **mọi luồng**. Chính chứng minh bất biến và chặn lỗi ở các mục3,11 mới đưa guarantee toán học. Bộ oracle giúp phát hiện lỗi lập trình như sai dấu threshold, quên tiêu thụ x khi hủy nhóm, xóa counter quá sớm hoặc merge bị mất candidate.

### 14.2. Chú ý chi phí của oracle

Dựng toàn bộ histogram và mảng input đòi O(U+N) bộ nhớ của **test harness**, không phải bộ nhớ MG cần trong production. Không được cộng phần brute-force/ground-truth vào yêu cầu bộ nhớ chính của sketch.

## 15. Có thể giảm chi phí lượt hai bằng gì?

### 15.1. Nguồn replayable

Cách trực tiếp và dễ kiểm chứng nhất:

1. Quét file lần1 bằng MG.
2. Giữ ≤k−1 ứng viên.
3. Quét file lần2, đếm đúng tần suất của ứng viên.
4. Trả `(key, exactCount)` vượt threshold.

Đây là thuật toán hai lượt, O(k) bộ nhớ phụ và thời gian tuyến tính/amortized theo N.

### 15.2. Lưu log có checkpoint

Dịch vụ online có thể ghi một log sự kiện có offset; khi cần thống kê một epoch, cố định `[offsetStart,offsetEnd)` rồi replay khoảng đó. Cần định nghĩa rõ cách xử lý sự kiện trùng lặp và thay đổi dữ liệu.

### 15.3. Đếm chính xác song song theo partition

Với distributed stream, mỗi worker sau khi nhận tập candidate **toàn cục** có thể đếm exact các candidate trong partition của mình; reducer cộng kết quả. Điều kiện là các partition **không chồng lặp** và bao phủ đúng snapshot.

### 15.4. Không có replay

Nếu không có cơ chế replay hoặc bộ nhớ bổ sung cho exact histograms, đầu ra phù hợp có thể là:

`(key, estimatedCount, lowerBound, upperBound)`,

với:

`lowerBound=m(x)`, `upperBound=m(x)+D`.

Đừng đặt tên field `exactCount` cho một ước lượng MG. Nếu nhu cầu là chỉ phát hiện ứng viên, một lượt là đủ; nếu hợp đồng cần tần suất **chính xác**, kiến trúc dữ liệu phải hỗ trợ việc đó.

## 16. Weighted streams, tổng hợp sự kiện và cập nhật âm

### 16.1. Sự kiện có trọng số dương

Một sự kiện `(x,w)` có w là số nguyên dương có thể được hiểu là **w lần xuất hiện của x**. Mở rộng stream bằng cách lặp x w lần rồi chạy MG là đúng về định nghĩa nhưng có thể quá chậm nếu w lớn.

Có các thuật toán **weighted Misra–Gries** xử lý một khối lượng dương cùng khóa theo từng đợt và trừ minimum thích hợp. Muốn dùng guarantee, phải thiết kế quy tắc cập nhật trọng số và ngân sách D nhất quán, không được chỉ cộng `w` vào counter hiện có rồi bỏ qua trường hợp đầy.

### 16.2. Phân biệt frequency theo số sự kiện và theo tổng trọng số

Nếu stream gồm `(x,w)`, có thể hỏi:

- Số **sự kiện** có khóa x.
- Tổng **weight** của các sự kiện có khóa x.

Hai loại heavy hitters này **khác nhau**. Phải công bố denominator là `N` hay tổng trọng số `W`.

### 16.3. Không hỗ trợ xóa theo bản MG insertion-only

MG chuẩn trong bài xử lý **luồng chỉ thêm** (*insertion-only*) với mỗi cập nhật là một lần xuất hiện. Nếu có cập nhật âm, đảo ngược sự kiện, hoặc sliding window mà sự kiện cũ hết hạn, không thể chỉ `counter[x]--` rồi vẫn giữ chứng minh cũ. Những sự kiện đã bị triệt tiêu từ trước không còn được lưu để đảo ngược chính xác.

Có thể dùng cấu trúc khác cho turnstile streams hoặc quản lý cửa sổ theo bucket/epoch và xây lại sketch, tùy guarantee cần đạt.

### 16.4. Sliding window

Bài toán “heavy hitters trong **W sự kiện gần nhất**” khác bài toán trên **toàn bộ prefix**. Nếu một khóa từng phổ biến nhưng lâu rồi không xuất hiện, sketch tích lũy không tự loại ảnh hưởng cũ.

Cần thuật toán dành cho sliding window, replay cửa sổ, hoặc phân đoạn/compaction được phân tích phù hợp. Không thể tự gọi MG nguyên luồng là MG sliding window.

## 17. Misra–Gries so với các thuật toán liên quan

| Thuật toán | Mục tiêu điển hình | Ý nghĩa bộ đếm |
|---|---|---|
| **Boyer–Moore majority vote** | Ứng viên >N/2 | k=2, cần lượt xác minh |
| **Misra–Gries** | Mọi ứng viên >N/k | ≤k−1 bộ đếm, **ước lượng dưới** với lỗi cộng ≤N/k |
| **Space-Saving** | Heavy hitters/top-k gần đúng | Thường thay khóa có counter nhỏ nhất, có cấu trúc error riêng |
| **Count-Min Sketch** | Ước lượng point-frequency nhiều khóa | Bảo đảm thường **ước lượng trên** với xác suất phụ thuộc width/depth và mô hình cập nhật |
| **Histogram đầy đủ** | Tần suất chính xác mọi khóa | O(U) bộ nhớ |
| **Reservoir sampling** | Mẫu đại diện của luồng | Không tự bảo đảm tìm mọi khóa >N/k |
| **Lossy Counting** | Frequent items theo sai số đặt trước | Chia bucket và làm sạch ứng viên với bound riêng |

Không hoán đổi proof của các thuật toán này. Đặc biệt MG không dùng “thay counter nhỏ nhất và gán min+1” của Space-Saving; Count-Min không mặc nhiên cho **exact frequencies** dù có bộ đếm lớn.

### 17.1. Heavy hitters khác top-k lớn nhất

Bài toán `f(x)>N/k` dùng một **ngưỡng tuyệt đối tương đối với N**. Bài toán **top-k keys** hỏi k khóa phổ biến nhất dù tần suất rất thấp và sát nhau. MG với k−1 counters không bảo đảm trả đủ **k khóa top-k** theo nghĩa xếp hạng, đặc biệt nếu các khóa đều có frequency≤N/k.

### 17.2. Tần suất sự kiện không phải tỷ lệ xác suất độc lập

MG không giả định các sự kiện IID, không cần phân phối ổn định, không cần dữ liệu ngẫu nhiên. Nó có guarantee worst-case cho một **chuỗi bất kỳ**.

## 18. Các lỗi triển khai và suy luận thường gặp

### Lỗi 1 — Giữ k counter rồi tuyên bố guarantee k−1

Ngưỡng và chứng minh phụ thuộc ngân sách counter; cần nhất quán.

### Lỗi 2 — Xem counter MG là exact frequency

Counter đã bị giảm bởi các nhóm triệt tiêu; thường nhỏ hơn f(x).

### Lỗi 3 — Dùng `m(x)>N/k` để lọc trước bước recount

Có thể loại heavy hitter thật do m(x) thấp hơn f(x).

### Lỗi 4 — Bỏ lượt hai nhưng gọi output là danh sách heavy hitter chính xác

Lượt một chỉ cho **candidate superset**.

### Lỗi 5 — Quên kiểm ứng viên dương tính giả

Trong luồng 1..11 với k=3, hai candidate cuối đều không heavy.

### Lỗi 6 — Dùng điều kiện `>=N/k` cho định nghĩa `>N/k`

Trường hợp tần suất đúng ngưỡng không đủ để gọi heavy.

### Lỗi 7 — Hiểu sai phép chia nguyên

Với tần suất nguyên, `f>N/k` tương đương `f>floor(N/k)`; không phải `f>=floor(N/k)`.

### Lỗi 8 — Dùng tổng counter thay độ dài stream N

Trong ví dụ20 sự kiện, counters chỉ cộng thành5, không thể dùng5 làm denominator.

### Lỗi 9 — Khi bảng đầy vẫn thêm x với counter1 trước khi giảm

Đó không còn là phép hủy k khóa đúng quy tắc và có thể vượt số counter.

### Lỗi 10 — Chỉ giảm một counter trong trường hợp3

Chứng minh hủy nhóm k khác nhau bị phá.

### Lỗi 11 — Không xóa counter về0

Để lại khóa0 chiếm ô có thể làm sai dung lượng và tạo ứng viên không cần thiết.

### Lỗi 12 — Cho phép counter âm

Bất biến survivor counters là **không âm**, khóa đang lưu phải có số đếm dương.

### Lỗi 13 — Đếm D sai

Mỗi lần bảng đầy gặp khóa ngoài bảng chỉ tăng D **một lần** trong bản đơn vị, dù giảm k−1 counters.

### Lỗi 14 — Khẳng định m(x)=f(x)−D cho mọi khóa

Đúng là `f(x)−D≤m(x)≤f(x)`; một khóa không nhất thiết bị xóa ở **mọi** nhóm.

### Lỗi 15 — Quên chứng minh khóa bị xóa có f(x)≤D

Đây là phần cốt lõi đảm bảo không bỏ sót.

### Lỗi 16 — Kết luận không có heavy hitter vì bảng từng rỗng ở giữa luồng

Khóa nặng về sau có thể xuất hiện và được giữ trong bảng cuối.

### Lỗi 17 — Chỉ thử một thứ tự dữ liệu

Kết quả candidates/counters phụ thuộc thứ tự; bảo đảm cần đúng với mọi hoán vị.

### Lỗi 18 — Quên k=2

Đó là trường hợp majority vote; vẫn phải recount.

### Lỗi 19 — Quên k>N

Khi bảng đủ rộng, D=0 và số đếm chính xác; chương trình không nên bị chia0 hay lỗi cấp phát vô lý.

### Lỗi 20 — Không xử lý N=0

Luồng rỗng phải trả rỗng, không chia số lần xuất hiện cho0.

### Lỗi 21 — Cho k=1 mà không có ngữ nghĩa rõ

Bản chuẩn nhận k≥2; cần validate để tránh bảng dung lượng âm/0.

### Lỗi 22 — Không tính bộ nhớ lưu khóa biến độ dài

O(k) entries không bảo đảm O(k) bytes nếu khóa là chuỗi tùy ý dài.

### Lỗi 23 — Tuyên bố O(1) worst-case cho mọi update

Trường hợp full+unseen quét O(k) counters; phân tích tổng/amortized mới giải thích thời gian tốt.

### Lỗi 24 — HashMap có O(1) deterministic worst-case trong mọi trường hợp

Thao tác băm có giả thiết về hàm băm và dữ liệu; không nên tuyên bố guarantee quá mức.

### Lỗi 25 — Quên recount phải đọc **cùng snapshot**

Hai lượt trên hai phiên dữ liệu khác nhau có thể tạo sai đáp án.

### Lỗi 26 — Gộp sketch bằng cách nối danh sách keys nhưng không giảm về k−1

Bảng có thể vượt giới hạn bộ nhớ và thiếu error analysis.

### Lỗi 27 — Gộp counter mà bỏ ngân sách D của từng partition

Sai cận f≤m+D cho toàn luồng.

### Lỗi 28 — Áp `N=C+kD` cho sketch gộp có lúc giảm m>k keys

Sau merge có thể chỉ có `C+kD≤N`.

### Lỗi 29 — Buộc merged counters phải giống direct counters

Hai sketch có thể khác nhưng đều có bảo đảm đúng và exact heavy set giống nhau sau recount.

### Lỗi 30 — Merge các partition overlap

Đếm trùng dữ liệu gây sai tần suất toàn cục.

### Lỗi 31 — Dùng k khác nhau nhưng merge không chuyển đổi bảo đảm

Thuật toán merge demo yêu cầu cùng k; không gộp tùy ý.

### Lỗi 32 — Bỏ qua overflow của counter/N

Luồng dài nên dùng số nguyên có miền đủ lớn và kiểm an toàn khi cộng.

### Lỗi 33 — Trộn weighted frequency với event count

Một lần xuất hiện có weight100 không giống 100 sự kiện nếu câu hỏi đếm **số sự kiện**.

### Lỗi 34 — Dùng MG insertion-only cho sự kiện xóa

Triệt tiêu trong quá khứ không thể đảo bằng cách giảm counter hiện tại.

### Lỗi 35 — Gọi heavy hitters toàn lịch sử là heavy hitters cửa sổ trượt

Cần định nghĩa và giữ đúng cửa sổ.

### Lỗi 36 — Gọi heavy hitter detection là top-k exact ranking

Ngưỡng >N/k không bảo đảm trả các top-k có tần suất dưới ngưỡng.

### Lỗi 37 — Lấy test random thay chứng minh worst-case

Oracle phát hiện bug; bất biến triệt tiêu mới chứng minh guarantee cho mọi stream.

### Lỗi 38 — Không kiểm case biên đúng bằng threshold

Nếu dùng sai `>=`, sẽ nhận khóa tần suất N/k, trái định nghĩa.

### Lỗi 39 — Dựa vào thứ tự HashMap để viết expected stdout

Thứ tự HashMap không phải API ổn định; demo dùng TreeMap để xuất kết quả xác định.

### Lỗi 40 — Giữ toàn bộ stream trong biến “sketch”

Một demo lưu int[] để test/replay là dễ hiểu, nhưng implementation streaming thực sự nên đọc từ iterator/file mà không giữ mọi phần tử trong RAM.

## 19. Bài tập có lời giải

### Bài 1 — Ngưỡng

N=100,k=5. Một khóa xuất hiện20 lần có là heavy hitter không?

**Đáp án:** Không, vì yêu cầu `f>20`; phải ít nhất21.

### Bài 2 — Số lượng heavy hitters

Với threshold `>N/k`, có thể có k heavy hitters không?

**Đáp án:** Không, tối đa k−1 khóa.

### Bài 3 — Dung lượng

k=7 cần lưu tối đa bao nhiêu bộ đếm?

**Đáp án:** 6.

### Bài 4 — Cập nhật đã có

Bảng `{A:3,B:2}`, k=3, x=A. Bảng mới?

**Đáp án:** `{A:4,B:2}`.

### Bài 5 — Còn ô trống

Bảng `{A:3}`, k=3, x=C. Bảng mới?

**Đáp án:** `{A:3,C:1}`.

### Bài 6 — Bảng đầy

Bảng `{A:3,B:1}`, k=3, x=C. Bảng mới?

**Đáp án:** `{A:2}`; C không được thêm trong lần hủy đó.

### Bài 7 — D của bài6

D tăng bao nhiêu?

**Đáp án:** 1, không phải2.

### Bài 8 — Bất biến khối lượng

N=20,k=3,sumCounters=5. D bằng?

**Đáp án:** `(20−5)/3=5`.

### Bài 9 — Chặn lỗi

k=3,N=20,D=5,m(A)=2. Tần suất thật của A nằm trong khoảng nào?

**Đáp án:** `2≤f(A)≤7`.

### Bài 10 — Khóa bị loại

N=20,k=3,D=5, khóa B không trong bảng. f(B) tối đa?

**Đáp án:** 5, nên không thể vượt20/3.

### Bài 11 — Heavy hitter bắt buộc còn lại

N=20,k=3, f(X)=8. X có chắc chắn là ứng viên?

**Đáp án:** Có, vì `8>20/3`.

### Bài 12 — Heavy hitter chưa chắc được xác nhận

Một ứng viên có m(X)=1. Có thể f(X)=1 không?

**Đáp án:** Có; ứng viên vẫn có thể là dương tính giả.

### Bài 13 — Bước verify

Ứng viên X có exactCount5, N=20,k=3. Có giữ X không?

**Đáp án:** Không, 5 không lớn hơn20/3.

### Bài 14 — Tại sao phải lượt hai?

**Đáp án:** Bộ đếm MG đã bị giảm trong các nhóm triệt tiêu, không bằng exactCount; lượt hai loại false positives và cung cấp frequency thật.

### Bài 15 — Bằng đúng threshold

N=6,k=3, mỗi khóa 1,2,3 xuất hiện2 lần. Heavy hitters?

**Đáp án:** Rỗng, vì `2=N/k`, không phải lớn hơn.

### Bài 16 — Trường hợp k=2

k=2 tìm ngưỡng nào?

**Đáp án:** Strict majority `f>N/2`, ứng viên kiểu Boyer–Moore.

### Bài 17 — Không có majority

Một ứng viên từ lượt một có chứng minh tồn tại majority không?

**Đáp án:** Không, cần recount.

### Bài 18 — k>N

N=3,k=8, có giảm counters lần nào không?

**Đáp án:** Không, D=0, mọi khóa xuất hiện được lưu đúng số lần.

### Bài 19 — Luồng rỗng

N=0, heavy hitters là gì?

**Đáp án:** Tập rỗng.

### Bài 20 — Tần suất trong map

Map cuối `{1:2,2:3}` của luồng N=20 có cho biết exact count là2 và3 không?

**Đáp án:** Không, ví dụ actual counts là7 và8.

### Bài 21 — Chi phí bộ nhớ

Nếu U=10^9 nhưng k=100, cần bao nhiêu counter?

**Đáp án:** Tối đa99, không phụ thuộc trực tiếp vào U (chưa kể kích thước biểu diễn khóa).

### Bài 22 — Amortized scan

Vì sao dù một lần hủy quét O(k) vẫn có thể phân tích tổng O(N) cho các vòng quét?

**Đáp án:** Mỗi lần hủy ứng với k phần tử bị triệt tiêu nên D≤N/k; tổng O(kD)=O(N).

### Bài 23 — HashMap và TreeMap

TreeMap có ưu điểm gì trong demo?

**Đáp án:** Thứ tự in khóa xác định; tra cứu O(log k) thay vì O(1) kỳ vọng của hashing.

### Bài 24 — Nhân bản sự kiện

Nếu cùng một sự kiện bị đưa vào hai partition rồi merge, frequency có đúng không?

**Đáp án:** Không; bị đếm hai lần nếu không có deduplication.

### Bài 25 — Merge budget

D_A=2,D_B=3, merge trừ thêm δ=4. Budget cuối?

**Đáp án:** 9.

### Bài 26 — Merge mass

Sau merge có luôn `N=C+kD` không?

**Đáp án:** Không, khi giảm m>k khóa chỉ có thể đảm bảo `C+kD≤N`.

### Bài 27 — Merge candidates

Nếu chạy direct và merge tạo counters khác nhau, có phải merge sai?

**Đáp án:** Không nhất thiết; kiểm cận error, không bỏ sót heavy và kết quả recount.

### Bài 28 — Gộp nhiều partition

Một tree merge có giữ bound không nếu các partition rời nhau và cùng k?

**Đáp án:** Có, do mỗi phép merge bảo toàn `m≤f≤m+D` và `kD≤N`.

### Bài 29 — Chọn k theo φ

Muốn bắt mọi khóa có tần suất hơn5% N, có thể chọn k nào?

**Đáp án:** k=20 (nếu strict >5%) hoặc lớn hơn, vì N/k≤0.05N.

### Bài 30 — Mục tiêu ≥5%

Nếu cần bắt các khóa **đúng bằng**5%, dùng k=20 có chắc chắn không?

**Đáp án:** Không; cần đặt `1/k<0.05` (ví dụ k=21) rồi verify theo điều kiện ≥5% N.

### Bài 31 — Recount trên snapshot khác

Luồng thay đổi giữa hai lượt có ảnh hưởng không?

**Đáp án:** Có; cần snapshot/offset nhất quán để N và exact frequency cùng một tập sự kiện.

### Bài 32 — Đếm có trọng số

100 sự kiện weight1 và một sự kiện weight100 có giống nhau khi tính **event frequency** không?

**Đáp án:** Không; chúng chỉ có thể giống nhau nếu bài toán định nghĩa theo tổng weight.

### Bài 33 — Window

Có thể lấy MG của lịch sử đầy đủ để gọi là MG cho 1.000 sự kiện cuối không?

**Đáp án:** Không, cần thuật toán/quy trình cửa sổ phù hợp.

### Bài 34 — Algorithm khác

Space-Saving có thay khóa có counter nhỏ nhất như bước3 của MG không?

**Đáp án:** Space-Saving có cơ chế thay khóa/min riêng; không giống MG giảm **tất cả** counter.

### Bài 35 — So true và estimate

N=100,k=5,D=12,m(X)=3. Có thể khẳng định f(X)=3 không?

**Đáp án:** Không; biết `3≤f(X)≤15`.

### Bài 36 — Bảo đảm không bỏ sót

Mệnh đề nào đúng: “x heavy ⇒ x ứng viên” hay “x ứng viên ⇒ x heavy”?

**Đáp án:** Chỉ mệnh đề thứ nhất được MG bảo đảm.

## 20. Checklist triển khai Misra–Gries + xác minh

1. Đã định nghĩa **đơn vị sự kiện** và khóa x?
2. Đã xác định N là số sự kiện của cùng một snapshot?
3. Đã công bố điều kiện `f(x)>N/k` có dấu nghiêm ngặt?
4. Đã validate k≥2?
5. Đã giới hạn bảng ở k−1 khóa?
6. Khi x đã có, tăng đúng bộ đếm của x?
7. Khi còn ô, chèn x với1?
8. Khi đầy và x mới, **giảm tất cả** counters?
9. Có bỏ phần tử x trong vòng triệt tiêu thay vì chèn?
10. Có xóa mọi counter giảm về0?
11. Có giữ các counter còn lại **dương**?
12. Có đếm D chính xác mỗi lần triệt tiêu?
13. Có kiểm bất biến `N=sumCounters+kD` cho bản direct?
14. Có kiểm `m(x)≤f(x)≤m(x)+D` bằng oracle ở test?
15. Có hiểu khóa **không trong bảng** có f(x)≤D?
16. Có chứng minh không bỏ sót khóa f>N/k?
17. Có hiểu vẫn có thể có **false positives**?
18. Có tránh lọc candidate bằng m(x)>N/k trước recount?
19. Lượt hai có bắt đầu exactCounts của mọi candidate từ0?
20. Có quét lại **toàn bộ** luồng đã dùng lượt một?
21. Có kiểm threshold từ exact count, không phải MG estimate?
22. Có đồng nhất snapshot/offset giữa hai lượt?
23. Có xử lý trường hợp không thể replay?
24. Có xử lý N=0/k>N/k=2?
25. Có kiểm trường hợp f=N/k bị loại theo dấu strict?
26. Có dùng long/đếm không overflow?
27. Có cân nhắc HashMap vs TreeMap và chi phí khóa?
28. Có phân biệt O(k) **bộ nhớ sketch** với mảng dữ liệu của demo?
29. Có thử luồng mọi khóa khác nhau và luồng rất lệch?
30. Có thử hoán vị thứ tự dữ liệu?
31. Nếu merge, các partition có rời nhau và phủ đúng N?
32. Nếu merge, hai sketch có cùng k?
33. Có cộng counters cùng khóa rồi giảm về k−1?
34. Có cộng D của partition và D do merge?
35. Có kiểm `sumCounters+kD≤N` sau merge?
36. Có chấp nhận merged counters khác direct counters nếu vẫn đúng guarantee?
37. Có kiểm exact heavy set sau merge bằng lượt replay toàn cục?
38. Có phân biệt frequency theo event và theo weight?
39. Có tránh dùng MG nguyên lịch sử cho sliding window/turnstile?
40. Có tách mục tiêu heavy hitters khỏi top-k exact ranking?
41. Có bộ oracle histogram độc lập với code MG?
42. Có kiểm ít nhất một tình huống **candidate giả nhưng output verified rỗng**?
43. Có ghi rõ cấp độ bảo đảm: candidate deterministic hay exact after verification?
44. Có thể giải thích bằng chứng triệt tiêu k khóa phân biệt?

**Kết luận:** Misra–Gries không phải máy đếm tần suất chính xác một lượt. Nó giữ tối đa **k−1 counter**, xóa theo nhóm **k phần tử khác nhau**, và bảo đảm rằng **mọi khóa có tần suất thực >N/k đều còn trong bảng**. Bất biến `N=sumCounters+kD` ở bản direct dẫn tới khoảng lỗi xác định `m(x)≤f(x)≤m(x)+D`, với `D≤N/k`. Nhưng **ứng viên có thể là false positive**; chỉ lượt hai đếm lại **trên cùng dữ liệu** mới loại được false positives và trả tần suất thật. Khi merge sketch, giữ ngân sách lỗi và bound `sumCounters+kD≤N` thay vì ép bất biến equality. Một triển khai đáng tin luôn phân biệt **ứng viên**, **ước lượng bộ đếm**, **tần suất đã kiểm chứng**, và giới hạn của các nguồn không thể replay.
