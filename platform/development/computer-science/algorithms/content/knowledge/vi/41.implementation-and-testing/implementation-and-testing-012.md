# Sinh dữ liệu có kiểm soát và thu nhỏ phản ví dụ

**Sinh dữ liệu có kiểm soát** (*controlled test-data generation*) và **thu nhỏ phản ví dụ** (*counterexample shrinking*) là hai kỹ thuật nền tảng của kiểm thử thuật toán. Kỹ thuật thứ nhất tạo các input có phân phối, kích thước, cấu trúc, ràng buộc và seed **được xác định rõ**; kỹ thuật thứ hai biến một test gây lỗi lớn thành một test **nhỏ, dễ đọc hơn nhưng vẫn giữ đúng lỗi**.

Ví dụ, một phiên bản Kadane khởi tạo `best=0` giải đúng biến thể **cho phép đoạn con rỗng**, nhưng **sai** nếu đề yêu cầu **đoạn con liên tiếp không rỗng**. Với mảng [-8,−3,−5], oracle trả −3 còn phiên bản buggy trả 0. Dùng phép xóa và giảm độ lớn giá trị, phản ví dụ có thể thu nhỏ thành **`[-1]`**: đúng là −1, buggy là 0. Một phần tử âm làm lộ ngay lỗi về hợp đồng, thay vì bắt người sửa code đọc một mảng dài hàng nghìn số.

Bài thuộc nhóm **Cài đặt và kiểm thử** của **Computer Science Algorithms**, đề bài trực tiếp **Sinh dữ liệu có kiểm soát và thu nhỏ phản ví dụ**. Trọng tâm gồm seed/caseId, generator theo mode, validity và failure predicate, **property-based testing**, kiểm thử đối chiếu (*differential testing*), kiểm thử biến hình (*metamorphic testing*), **delta debugging (ddmin)**, value shrinking, điều kiện tối giản cục bộ, khó khăn với input có cấu trúc hoặc flaky failure và thực hành bằng **Java 17+ độc lập**.

Mục tiêu sau bài: tự tạo test có thể phát lại; chọn oracle độc lập; sinh đúng miền hợp lệ và đúng tình huống biên; thu nhỏ input mà không biến lỗi ban đầu thành một lỗi khác; biết vì sao **1-minimal không đồng nghĩa tối thiểu toàn cục**; viết regression test rõ ràng từ counterexample cuối.

## 1. Kiến trúc một test sinh tự động

Hãy tách bốn thành phần:

1. **Generator `G(seed,caseId)`** tạo input x. Generator cần phù hợp tiền điều kiện và phân phối mong muốn.
2. **Validity predicate `V(x)`** trả true khi x hợp lệ theo đề (kích thước, miền giá trị, sortedness, shape, connectedness, grammar...).
3. **Oracle/property `O(x)`** là tiêu chuẩn đúng: kết quả exact của brute-force, các invariant, hoặc quan hệ giữa các input.
4. **Failure predicate `F(x)`** trả true khi input hợp lệ làm lộ đúng failure cần nghiên cứu.

Một dạng dễ hiểu:

**`F(x)=V(x) ∧ [implementation(x)≠oracle(x)]`**.

Trong code, luôn **kiểm V trước**, mới chạy hai lời giải. Oracle không nhất thiết định nghĩa trên input invalid. Với shrinking, **mọi candidate** cũng phải qua V; một phản ví dụ nhỏ hơn nhưng mất tiền điều kiện không chứng minh bug của thuật toán gốc.

### Failure signature là gì?

Nếu một test gốc sai kết quả nhưng shrink lại tạo một NullPointerException, predicate tổng quát “có lỗi bất kỳ” vẫn true nhưng **lỗi cuối có thể không còn cùng nguyên nhân**. Nên dùng signature như:
- Tên assertion/property thất bại.
- Loại output mismatch.
- Exception type và stack frame quan trọng.
- Mã lỗi hoặc invariant bị phá.

Chọn đúng failure signature đặc biệt quan trọng khi một input có thể gây nhiều lỗi độc lập. Không thể kết luận một implementation sai chỉ vì một oracle/test harness cũng chứa bug.

## 2. Example testing, property-based testing, differential testing

**Example-based testing:** dùng các input/expected được viết tay; dễ hiểu và thích hợp regression, nhưng phạm vi nhỏ.

**Randomized testing:** rút nhiều input bằng PRNG; cần seed, phân phối và oracle.

**Property-based testing:** xác định thuộc tính phải đúng với mọi input hợp lệ, tự sinh nhiều input rồi báo counterexample và có thể tự shrink.

**Differential testing:** đối chiếu implementation tối ưu với một lời giải độc lập, thường chậm nhưng ngắn, trên input nhỏ. Ví dụ Kadane O(n) so với brute O(n²).

**Metamorphic testing:** khi chưa tính được output exact, kiểm mối quan hệ giữa input và input đã biến đổi. Ví dụ:
- `sort(sort(a))=sort(a)` trong hợp đồng deterministic.
- Chuyển vị ma trận hai lần trả ma trận ban đầu.
- Tổng trên đoạn nối bằng tổng hai đoạn kề nhau.
- Đổi tên đỉnh đồ thị nhất quán không làm thay đổi khoảng cách đường đi sau remap.

Một property đơn lẻ có thể quá yếu. Hàm sort luôn trả [] có thể thỏa idempotence nhưng sai vì mất toàn bộ item. Cần kiểm thêm **sortedness + permutation**, và **stability** khi có yêu cầu.

## 3. Các mode dữ liệu cần thiết kế có chủ đích

Một generator mảng số nguyên chất lượng nên có các mode:

| Mode | Những lỗi dễ phát hiện |
|---|---|
| Empty | Truy cập a[0], nhầm trường hợp rỗng |
| Singleton | Off-by-one, điều kiện dừng |
| All-negative | Kadane nonempty, phép max với identity=0 |
| All-positive | Tổng, overflow, điều kiện biên |
| All-equal | Tính ổn định, partition nhiều duplicate |
| Sorted | Binary search, trường hợp pivot trên input có thứ tự |
| Reverse sorted | Pivot xấu, so sánh đảo |
| Alternating signs | Prefix/suffix, trạng thái tối ưu thay đổi |
| Few distinct values | Duplicates, tie-breaking |
| Sparse spikes | Nhánh xử lý phần tử khác 0 |
| Integer extrema | Tràn số, dấu, hàm abs |
| Medium/large inputs | Stack, timeout, GC, độ phức tạp |

Nếu chỉ sinh từng item đều từ một miền cực rộng, input trùng khóa rất hiếm và lỗi stable sort có thể không xuất hiện. Nếu chỉ rút n đều trong 0..100000, n=0 hoặc n=1 mỗi loại có xác suất rất nhỏ. **Số lượng test lớn không bù được một distribution thiếu góc khó.**

### Phân phối trộn

Có thể dành quota:
- Nhiều test nhỏ cho oracle brute.
- Test biên n∈{0,1,2,3,threshold−1,threshold,threshold+1}.
- Test có cấu trúc: sorted, reverse, all equal, graph chain/star, ma trận chữ nhật.
- Test random nhiều dạng.
- Một lượng nhỏ test cực lớn cho stress.

Nếu lỗi hiếm xảy ra với xác suất p ở mỗi case độc lập, sau T case xác suất chưa gặp là `(1−p)^T`. Khi p rất nhỏ, chủ động tạo mode gây lỗi thường hiệu quả hơn nhiều so với chỉ tăng T.

## 4. Seed và caseId để tái lập

Một PRNG dùng liên tục có thể tái lập khi giữ nguyên seed và **mọi lần rút random trước đó**. Nhưng nếu sửa generator để rút thêm một số ở case thứ 3, các case sau có thể thay đổi hết. Vì vậy một thiết kế tiện lợi là:

**`caseSeed=mix(masterSeed,caseId)`**.

~~~text
for caseId=0..T-1:
    rng = PRNG(caseSeed(masterSeed,caseId))
    input = generate(rng, mode(caseId))
    test(input)
~~~

Mỗi case có thể chạy lại **độc lập**. Cách mix kiểu SplitMix64 có khả năng khuếch tán bit; nó không biến PRNG thành RNG mật mã. Trong mã Java, overflow long bên trong mix là **cố ý** modulo 2⁶⁴.

Một report phát lại nên ghi:
- Test name, masterSeed, caseId.
- Generator version/mode.
- **Input thực tế đã sinh**.
- Expected/actual và failure signature.
- Runtime/JDK/OS/locale/concurrency configuration khi có liên quan.

**Seed không tự kiểm soát scheduler, thời gian, mạng, file system hoặc GC**. Test flaky cần được xử lý riêng; cùng seed vẫn có thể chạy khác nhau nếu thuật toán có race.

## 5. Generator chỉ được tạo input hợp lệ

Một số tiền điều kiện điển hình:

**Binary search/lower bound:** mảng phải sorted không giảm. Random array chưa sort không phải test hợp lệ cho binary search.

**Dijkstra:** trọng số không âm theo giả thiết thuật toán chuẩn.

**Tree:** connected và acyclic; khi n≥1 phải có n−1 cạnh. **DAG:** không có chu trình; nếu bài yêu cầu reachable(s,t), xóa cạnh không được làm mất reachability.

**Matrix multiplication:** A(m×p) và B(p×n) phải có chiều trong khớp; mỗi hàng có đúng số cột. Nếu xóa một cột A khi shrink, phải xóa **hàng B tương ứng** mới giữ shape.

**Stateful operation sequence:** nếu API cấm delete(x) trước insert(x), generator và shrinker đều phải tôn trọng quy tắc.

**Unicode:** không cắt một surrogate pair ở ranh giới UTF-16 nếu input yêu cầu valid Unicode, hoặc không cắt token làm JSON mất grammar.

**Nonempty maximum subarray:** cần n≥1. Xóa phần tử cuối cùng tạo [] là một candidate **invalid**, không chấp nhận dù code buggy trả 0.

Đây là lý do **validity** phải độc lập với **failure**.

## 6. Chọn oracle thực sự độc lập

Bài toán input nhỏ thường có lời giải brute-force đơn giản:

| Implementation đang kiểm | Oracle |
|---|---|
| Kadane nonempty | Liệt kê mọi đoạn con không rỗng |
| Binary search | Quét trái sang phải |
| Segment tree range sum | Cộng trực tiếp các phần tử |
| KMP streaming | So pattern tại mọi vị trí trong chuỗi đầy đủ |
| Dijkstra không âm | Bellman–Ford trên đồ thị nhỏ |
| Matrix tiling | Nhân ba vòng i-j-k trực tiếp |
| Stable partition | Lọc nguyên thứ tự input qua ba nhóm |
| Sorting | Sortedness + permutation + stability nếu cần |

Ví dụ maximum subarray có công thức oracle:

**`best=max_{0≤l<r≤n}Σ_{i=l}^{r−1}a[i]`**, n≥1.

Oracle tính mọi đoạn có hai vòng for, O(n²). Kadane tính O(n) nhờ recurrence. Hai cách **khác cấu trúc**, nên bug trong recurrence khó bị sao chép vào oracle.

Oracle cũng có thể sai. Ví dụ khi test stable three-way partition bằng prefix counts, cần đếm `counts[classOf(a[i])]`, không phải `counts[a[i]]`. Nếu a[i] âm, dùng giá trị làm index có thể gây lỗi chỉ trong test harness. Vì vậy mỗi khi có mismatch:
1. Kiểm input hợp lệ.
2. Tính bằng tay ví dụ nhỏ.
3. Chạy một oracle thứ ba hoặc một property khác.
4. Kiểm state/aliasing và serialization.
5. Chỉ sau đó kết luận thuật toán chính sai.

## 7. Phản ví dụ cố ý: sai hợp đồng Kadane

Đề yêu cầu **maximum sum của đoạn con không rỗng**. Một Kadane đúng:
- Khởi tạo `current=best=a[0]`.
- Với i≥1: `current=max(a[i],current+a[i])`.
- `best=max(best,current)`.

Một bản buggy dưới hợp đồng này lại đặt `current=best=0` rồi luôn cho phép reset current về 0. Nó tương ứng với một bài **khác**: cho phép chọn đoạn rỗng.

Ví dụ:

~~~text
Input: [-8, -3, -5]
Oracle: -3
Buggy: 0
Mismatch: true
~~~

Input này hợp lệ và phơi bày lỗi. Để dễ chẩn đoán hơn, có thể giảm thành:

~~~text
Input: [-1]
Oracle: -1
Buggy: 0
Mismatch: true
~~~

Phản ví dụ thứ hai cho thấy chỉ một số âm cũng đủ. Nhưng phải **giữ hợp đồng nonempty**: [] không được chọn làm “minimal counterexample”.

## 8. Delta debugging (ddmin) theo phép xóa khối

**Ddmin** giảm độ dài input bằng cách thử bỏ **các chunk liên tiếp**, kiểm xem candidate vẫn hợp lệ và vẫn fail.

~~~text
ddmin(current, valid, fails):
    require valid(current) and fails(current)
    parts = 2

    while len(current) >= 2:
        chunk = ceil(len(current)/parts)
        reduced = false

        for each contiguous chunk [start,end):
            candidate = current without [start,end)
            if valid(candidate) and fails(candidate):
                current = candidate
                parts = max(2,parts-1)
                reduced = true
                break

        if not reduced:
            if parts >= len(current): break
            parts = min(len(current),2*parts)

    return current
~~~

Chấp nhận xóa chunk làm **chiều dài giảm nghiêm ngặt**, nên không thể lặp vô hạn ở nhánh giảm. Nếu không xóa được, tăng số phần tới mức thử từng phần tử. Với phản ví dụ [-8,−3,−5], xóa [−8,−3] còn [−5], vẫn mismatch; xóa phần tử cuối sẽ thành [], invalid. Ddmin kết thúc ở [−5].

### 1-minimal không phải globally minimal

Một input x gọi là **1-minimal với phép xóa phần tử** nếu không thể xóa **một item** nào mà vẫn giữ validity và failure. Nó không có nghĩa:
- Đây là input ngắn nhất trên toàn bộ miền.
- Không thể xóa nhiều item đồng thời để được input nhỏ hơn.
- Không thể thay giá trị rồi tiếp tục xóa.
- Mọi thứ tự shrink đều cho cùng kết quả.

Một failure predicate có thể **không đơn điệu** theo phép xóa: một lần xóa làm bug biến mất, xóa tiếp có thể làm bug xuất hiện lại. Một shrinker greedy giữ F=true sau từng bước không thể đi xuyên qua trạng thái F=false. Vì vậy nên báo cáo **local minimality theo các transformation cụ thể**, không tuyên bố global optimum.

## 9. Value shrinking: giảm các con số

Sau ddmin, [−5] vẫn có thể trở nên đơn giản hơn. Thử:
1. 0.
2. `sign(value)`, ví dụ −1.
3. `value/2` (làm tròn về 0).
4. Domain-specific boundaries như 1,−1,k,n.

Mọi candidate phải:
- Giữ validity.
- Giữ failure.
- Làm giảm một **thước đo có thứ tự tốt** như magnitude.

Với −5:
- 0 có magnitude thấp nhưng bug biến mất: oracle=buggy=0.
- −1 nhỏ hơn và vẫn fail: oracle=−1, buggy=0.
- Tới −1, số nguyên có magnitude thấp hơn duy nhất là 0, nhưng 0 không còn fail.

Kết quả cuối là **`[-1]`**.

**Chú ý Integer.MIN_VALUE:** `Math.abs(Integer.MIN_VALUE)` trong int vẫn âm do overflow. Code Java dùng **`Math.abs((long)value)`**, an toàn cho toàn bộ int, khi so magnitude.

### Không dùng thuật toán shrink có thể tăng trở lại

Nếu thay 3→2 rồi 2→3 tùy điều kiện mà không có measure nghiêm ngặt, shrinker có thể chạy vô hạn. Với phép giảm length trước, magnitude sau, cặp thước đo (độ dài, tổng magnitude) giảm theo thứ tự từ điển; khi mọi candidate đều làm giảm, thuật toán sẽ dừng.

## 10. Shrinking dữ liệu có cấu trúc

**Sorted arrays:** xóa item vẫn giữ sortedness, nhưng thay giá trị có thể phá. Kiểm sortedness sau mỗi candidate, hoặc sinh/shrink trên representation các nonnegative gaps.

**Connected graphs:** xóa edge có thể mất connectedness. Chạy BFS kiểm lại; xóa vertex phải remap IDs và giữ source/target.

**DAGs:** xóa cạnh giữ acyclicity; nhưng nếu yêu cầu có đường đi s→t, phải kiểm riêng reachability.

**Matrix pairs:** khi test A(m×p)·B(p×n), xóa cột k của A phải xóa hàng k của B để giữ compatibility.

**JSON/source code:** shrink ở cấp AST/token, không xóa byte tùy ý làm hỏng grammar. Có thể bỏ field optional, thu nhỏ literal, bỏ statement mà vẫn bảo đảm biến được định nghĩa.

**Unicode strings:** thu nhỏ theo code point, không cắt giữa UTF-16 surrogate pair; nếu contract yêu cầu grapheme hoặc NFC, kiểm lại sau thay đổi.

**Operation sequences:** lệnh update/delete/query có thể có quan hệ phụ thuộc. Bỏ một insert nhưng giữ delete tương ứng có thể chuyển test sang invalid operation. Phải kiểm toàn bộ state transition sau khi xóa nhóm lệnh.

**Concurrency tests:** bug race chỉ xuất hiện với đủ worker hoặc đủ tải; thu nhỏ xuống một worker rồi mất race không phải một shrink hợp lệ để điều tra race ban đầu.

## 11. Shrink failure phải giữ được khả năng tái lập

Một predicate nên:
- Không mutate input.
- Reset trạng thái của implementation trước mỗi lần gọi.
- Dùng cùng hợp đồng và oracle.
- Giữ failure signature.
- Có kết quả xác định hoặc xử lý flakiness có chủ đích.
- Có ngân sách số lần gọi/thời gian.
- Lưu best-so-far nếu hết ngân sách.

Nếu một test timeout phụ thuộc CPU load, một lần chạy candidate không đủ để quyết định F. Có thể dùng nhiều lần chạy và tỷ lệ tái hiện, nhưng phải ghi rõ tiêu chuẩn. Seed chỉ kiểm soát PRNG, **không kiểm soát lịch chạy thread**.

### Caching predicate

Với F deterministic, cache theo canonical input có thể giảm số lần oracle chạy lại. Nhưng với race/flaky bug, cache một lần pass/fail có thể làm sai quyết định shrinking. Không áp dụng cache máy móc khi F không ổn định.

## 12. Kiểm thử lower bound và phép phân hoạch ổn định

**Lower bound** trên mảng sorted là index đầu tiên thỏa `a[i]≥target`; nếu không có, trả n. Đối chiếu với **linear scan**. Sinh mảng từ random values rồi **sort trước khi gọi**; một nửa target được chọn từ mảng để tạo nhiều duplicate hits, nửa còn lại chọn từ miền lân cận.

**Stable three-way partition** chọn pivot p và phân item theo:
- Class 0: key<p.
- Class 1: key=p.
- Class 2: key>p.

Để giữ thứ tự occurrence, cần biết **exclusive prefix count** của từng class. Cho item i thuộc class c, nếu `before[i]` là số item class c trước i, thì vị trí scatter:

**`dest(i)=start[c]+before[i]`**,

với starts là [0, countLess, countLess+countEqual]. Mọi item cùng class có before khác nhau; các class chiếm các vùng output rời nhau, nên không có hai item ghi cùng ô. Bản Java trả **chỉ số nguồn** chứ không trả giá trị, giúp kiểm stability khi có duplicate values.

Oracle độc lập làm ba lượt:
- Lấy tất cả index có key<p theo thứ tự gốc.
- Lấy tất cả index có key=p.
- Lấy tất cả index có key>p.

Nếu code prefix sai nhưng chỉ so output values, bug đảo hai occurrence bằng khóa có thể bị che.

### Ví dụ

~~~text
Keys:       [3, 1, 2, 3, 1, 2]
OriginalID: [0, 1, 2, 3, 4, 5]
Pivot:      2
Output IDs: [1, 4, 2, 5, 0, 3]
Output key: [1, 1, 2, 2, 3, 3]
~~~

## 13. Java 17+ hoàn chỉnh

Mã sau là một chương trình **độc lập**, không cần JUnit hay thư viện ngoài JDK. Nó gồm:
- `generateCase` sinh dữ liệu theo 10 mode và mỗi case một seed.
- `bruteNonemptyMax` O(n²) cùng `kadaneNonempty` O(n).
- `buggyAllowEmptyKadane` giữ lỗi cố ý về nonempty contract.
- `ddmin` cho deletion, `shrinkMagnitude` cho giảm magnitude.
- `lowerBound` và oracle linear scan.
- `stablePrefixPartition` và oracle three-pass.
- 17.000 case Kadane (15.300 nonempty), 19.000 lower-bound, 20.000 stable-partition và 3.500 ca shrink toàn âm.

Các phép cộng trong maximum subarray dùng long, trong khi generator có tối đa 48 phần tử int; vì vậy tổng độ lớn chắc chắn nằm trong long. Hàm `check` ném AssertionError trực tiếp, không phụ thuộc flag `-ea` của Java.

Lưu tệp **`ControlledGeneratorShrinkerDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;
import java.util.function.Predicate;

public final class ControlledGeneratorShrinkerDemo {
    private static final long MASTER_SEED = 5462026L;

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    // Per-case SplitMix64-like seed mixing. Signed long
    // overflow in these bit operations is intentional.
    private static long caseSeed(long master, long id) {
        long z = master
                + 0x9E3779B97F4A7C15L * (id + 1L);
        z = (z ^ (z >>> 30))
                * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27))
                * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }

    // Mode 0 is empty; modes 1..9 are nonempty.
    private static int[] generateCase(long seed, int id) {
        int mode = id % 10;
        if (mode == 0) {
            return new int[0];
        }

        SplittableRandom rng = new SplittableRandom(
                caseSeed(seed, id));
        int n = 1 + rng.nextInt(48);
        int[] out = new int[n];
        int common = rng.nextInt(-20, 21);

        for (int i = 0; i < n; i++) {
            out[i] = switch (mode) {
                case 1 -> -1 - rng.nextInt(100);
                case 2 -> rng.nextInt(101);
                case 3 -> common;
                case 4, 5 -> rng.nextInt(-20, 21);
                case 6 -> i % 2 == 0 ? -50 : 50;
                case 7 -> i == n / 2
                        ? Integer.MAX_VALUE : 0;
                case 8 -> rng.nextInt(-2, 3);
                default -> rng.nextInt(10) == 0
                        ? Integer.MIN_VALUE
                        : rng.nextInt(-10000, 10001);
            };
        }

        if (mode == 4 || mode == 5) {
            Arrays.sort(out);
            if (mode == 5) {
                for (int i = 0, j = n - 1;
                        i < j; i++, j--) {
                    int t = out[i];
                    out[i] = out[j];
                    out[j] = t;
                }
            }
        }
        return out;
    }

    // O(n^2) independent oracle, nonempty contract.
    private static long bruteNonemptyMax(int[] a) {
        if (a.length == 0) {
            throw new IllegalArgumentException(
                    "Nonempty maximum requires n>=1");
        }
        long best = Long.MIN_VALUE;

        for (int lo = 0; lo < a.length; lo++) {
            long sum = 0L;
            for (int hi = lo; hi < a.length; hi++) {
                sum += a[hi];
                best = Math.max(best, sum);
            }
        }
        return best;
    }

    // O(n) correct Kadane for NONEMPTY subarrays.
    private static long kadaneNonempty(int[] a) {
        if (a.length == 0) {
            throw new IllegalArgumentException(
                    "Nonempty maximum requires n>=1");
        }
        long current = a[0];
        long best = current;

        for (int i = 1; i < a.length; i++) {
            current = Math.max(
                    (long) a[i], current + a[i]);
            best = Math.max(best, current);
        }
        return best;
    }

    // Deliberately wrong for the NONEMPTY contract.
    private static long buggyAllowEmptyKadane(int[] a) {
        long current = 0L;
        long best = 0L;
        for (int value : a) {
            current = Math.max(0L, current + value);
            best = Math.max(best, current);
        }
        return best;
    }

    private static boolean badKadaneFails(int[] a) {
        return a.length > 0
                && bruteNonemptyMax(a)
                   != buggyAllowEmptyKadane(a);
    }

    // Create a new array without the interval [start,end).
    private static int[] removeRange(
            int[] a, int start, int end) {
        int[] result = new int[
                a.length - (end - start)];
        System.arraycopy(a, 0, result, 0, start);
        System.arraycopy(
                a, end, result, start, a.length - end);
        return result;
    }

    // Delete contiguous chunks; validity is separate.
    private static int[] ddmin(
            int[] input,
            Predicate<int[]> valid,
            Predicate<int[]> fails) {
        if (!valid.test(input) || !fails.test(input)) {
            throw new IllegalArgumentException(
                    "Expected a valid failing input");
        }

        int[] current = input.clone();
        int parts = 2;
        while (current.length >= 2) {
            int chunk = 1 + (current.length - 1) / parts;
            boolean reduced = false;

            for (int start = 0;
                    start < current.length;
                    start += chunk) {
                int end = start + Math.min(
                        chunk, current.length - start);
                int[] candidate = removeRange(
                        current, start, end);

                if (valid.test(candidate)
                        && fails.test(candidate)) {
                    current = candidate;
                    parts = Math.max(2, parts - 1);
                    reduced = true;
                    break;
                }
            }

            if (!reduced) {
                if (parts >= current.length) {
                    break;
                }
                int halfCeiling =
                        1 + (current.length - 1) / 2;
                parts = parts >= halfCeiling
                        ? current.length : parts * 2;
            }
        }
        return current;
    }

    // Each accepted replacement strictly reduces abs(value).
    private static int[] shrinkMagnitude(
            int[] input,
            Predicate<int[]> valid,
            Predicate<int[]> fails) {
        if (!valid.test(input) || !fails.test(input)) {
            throw new IllegalArgumentException(
                    "Expected a valid failing input");
        }

        int[] current = input.clone();
        boolean changed;
        do {
            changed = false;

            outer:
            for (int i = 0; i < current.length; i++) {
                int value = current[i];
                int[] proposals = {
                    0,
                    Integer.signum(value),
                    value / 2
                };

                for (int smaller : proposals) {
                    if (Math.abs((long) smaller)
                            >= Math.abs((long) value)) {
                        continue;
                    }

                    int[] candidate = current.clone();
                    candidate[i] = smaller;
                    if (valid.test(candidate)
                            && fails.test(candidate)) {
                        current = candidate;
                        changed = true;
                        break outer;
                    }
                }
            }
        } while (changed);
        return current;
    }

    private static boolean deletionOneMinimal(
            int[] a,
            Predicate<int[]> valid,
            Predicate<int[]> fails) {
        for (int i = 0; i < a.length; i++) {
            int[] candidate = removeRange(a, i, i + 1);
            if (valid.test(candidate)
                    && fails.test(candidate)) {
                return false;
            }
        }
        return true;
    }

    // a MUST be sorted nondecreasing.
    private static int lowerBound(int[] a, int target) {
        int lo = 0;
        int hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    private static int linearLowerBound(
            int[] a, int target) {
        int i = 0;
        while (i < a.length && a[i] < target) {
            i++;
        }
        return i;
    }

    private static int group(int key, int pivot) {
        return key < pivot ? 0
                : key == pivot ? 1 : 2;
    }

    // Return original indices, not duplicate-prone values.
    private static int[] stablePrefixPartition(
            int[] a, int pivot) {
        int n = a.length;
        int[] classes = new int[n];
        int[] before = new int[n];
        int[] counts = new int[3];

        for (int i = 0; i < n; i++) {
            int category = group(a[i], pivot);
            classes[i] = category;
            before[i] = counts[category];
            counts[category]++;
        }

        int[] start = {
            0,
            counts[0],
            counts[0] + counts[1]
        };
        int[] out = new int[n];
        for (int i = 0; i < n; i++) {
            int destination =
                    start[classes[i]] + before[i];
            out[destination] = i;
        }
        return out;
    }

    // Independent 3-pass stable grouping oracle.
    private static int[] referencePartition(
            int[] a, int pivot) {
        int[] out = new int[a.length];
        int next = 0;
        for (int category = 0; category < 3; category++) {
            for (int i = 0; i < a.length; i++) {
                if (group(a[i], pivot) == category) {
                    out[next++] = i;
                }
            }
        }
        return out;
    }

    private static void randomizedCorrectnessTests() {
        int nonempty = 0;
        int empty = 0;

        // Exactly every tenth generated case is empty.
        for (int id = 0; id < 17000; id++) {
            int[] a = generateCase(MASTER_SEED, id);
            if (a.length == 0) {
                empty++;
                continue;
            }
            check(bruteNonemptyMax(a)
                    == kadaneNonempty(a),
                    "Kadane mismatch, case=" + id);
            nonempty++;
        }
        check(nonempty == 15300 && empty == 1700,
                "Wrong generator mode counts");
        System.out.println(
                "Kadane differential: 15300 PASS; "
                + "empty cases: 1700");

        for (int id = 0; id < 19000; id++) {
            SplittableRandom rng = new SplittableRandom(
                    caseSeed(MASTER_SEED, 20000L + id));
            int n = rng.nextInt(71);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-20, 21);
            }
            Arrays.sort(a);

            int target = n > 0 && id % 2 == 0
                    ? a[rng.nextInt(n)]
                    : rng.nextInt(-23, 24);
            check(lowerBound(a, target)
                    == linearLowerBound(a, target),
                    "Lower bound mismatch, case=" + id);
        }
        System.out.println("Lower bound: 19000 PASS");

        for (int id = 0; id < 20000; id++) {
            SplittableRandom rng = new SplittableRandom(
                    caseSeed(MASTER_SEED, 50000L + id));
            int n = rng.nextInt(91);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-8, 9);
            }
            int pivot = rng.nextInt(-10, 11);

            check(Arrays.equals(
                    stablePrefixPartition(a, pivot),
                    referencePartition(a, pivot)),
                    "Stable partition mismatch, case=" + id);
        }
        System.out.println(
                "Stable prefix partition: 20000 PASS");
    }

    private static void randomizedShrinkTests() {
        Predicate<int[]> valid = a -> a.length > 0;
        Predicate<int[]> fails =
                ControlledGeneratorShrinkerDemo::badKadaneFails;

        for (int id = 0; id < 3500; id++) {
            SplittableRandom rng = new SplittableRandom(
                    caseSeed(MASTER_SEED, 80000L + id));
            int n = 1 + rng.nextInt(55);
            int[] a = new int[n];

            for (int i = 0; i < n; i++) {
                a[i] = -1 - rng.nextInt(5000);
            }
            check(fails.test(a),
                    "All-negative input must expose bug");

            int[] minimal = shrinkMagnitude(
                    ddmin(a, valid, fails),
                    valid, fails);
            check(Arrays.equals(minimal, new int[]{-1}),
                    "Unexpected negative minimal input");
            check(deletionOneMinimal(
                    minimal, valid, fails),
                    "Not deletion 1-minimal");
        }
        System.out.println(
                "Shrink all-negative failures: 3500 PASS");
    }

    public static void main(String[] args) {
        int[] original = {-8, -3, -5};
        Predicate<int[]> valid = a -> a.length > 0;
        Predicate<int[]> fails =
                ControlledGeneratorShrinkerDemo::badKadaneFails;

        check(valid.test(original) && fails.test(original),
                "Expected a failing example");
        int[] reduced = shrinkMagnitude(
                ddmin(original, valid, fails),
                valid, fails);
        check(Arrays.equals(reduced, new int[]{-1}),
                "Expected the reduced input [-1]");

        System.out.println(
                "Original: " + Arrays.toString(original)
                + "; oracle=" + bruteNonemptyMax(original)
                + "; buggy=" + buggyAllowEmptyKadane(original));
        System.out.println(
                "Shrunk: " + Arrays.toString(reduced)
                + "; oracle=" + bruteNonemptyMax(reduced)
                + "; buggy=" + buggyAllowEmptyKadane(reduced));
        System.out.println(
                "Deletion 1-minimal: "
                + deletionOneMinimal(reduced, valid, fails));

        randomizedCorrectnessTests();
        randomizedShrinkTests();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 ControlledGeneratorShrinkerDemo.java
java ControlledGeneratorShrinkerDemo
~~~

**Stdout chính xác:**

~~~text
Original: [-8, -3, -5]; oracle=-3; buggy=0
Shrunk: [-1]; oracle=-1; buggy=0
Deletion 1-minimal: true
Kadane differential: 15300 PASS; empty cases: 1700
Lower bound: 19000 PASS
Stable prefix partition: 20000 PASS
Shrink all-negative failures: 3500 PASS
~~~

### Giải thích output

**Original:** input [-8,−3,−5] có nonempty max là −3; bản buggy cho phép tổng đoạn rỗng 0.

**Shrunk:** sau deletion và giảm magnitude, [-1] vẫn cho mismatch, nên phản ví dụ một phần tử giải thích bug trực tiếp.

**Deletion 1-minimal:** xóa phần tử duy nhất sẽ tạo [], không hợp lệ đối với hàm nonempty.

**Kadane:** trong 17.000 case, mode 0 ở mỗi case thứ mười là empty: đúng 1.700 ca rỗng được đếm và không gọi hàm nonempty. 15.300 ca còn lại so với brute exact.

**Lower bound:** 19.000 mảng sorted với duplicates và target có/không có được so với linear first-at-least oracle.

**Stable partition:** 20.000 case so danh sách **original indices**, nên có thể phát hiện đảo thứ tự các occurrence bằng khóa.

**Shrinking:** 3.500 mảng âm ngẫu nhiên khác nhau, tất cả đều làm buggy Kadane trả sai; với phép shrink đã thiết kế, đều được đưa về [-1]. Đây là một **kết quả riêng của failure predicate này**, không phải bảo đảm cho mọi bug.

Trong Java, dùng **long** cho tổng các số int trong các dãy độ dài ≤48; tổng độ lớn nằm gọn trong long. Hàm check ném AssertionError trực tiếp, không phụ thuộc `-ea` như từ khóa `assert`.

## 14. Bằng chứng tính đúng của ddmin và value shrinking

**Invariant của ddmin:** current luôn valid và failing:
- Đầu hàm có precondition kiểm hai điều kiện.
- Candidate được gán thành current **chỉ khi** valid và failing.
- Do quy nạp, invariant đúng trong toàn bộ vòng lặp.

Khi chấp nhận xóa chunk, số phần tử giảm nghiêm ngặt. Khi chưa giảm, số partitions tăng cho tới mức thử từng phần tử. Vì vậy thuật toán dừng với một input không thể tiếp tục giảm bằng các phép deletion đã thử.

**Invariant của value shrinker:** từng lần thay chỉ giảm `Math.abs((long)value)` và vẫn giữ valid+failing. Với int, tổng magnitude là số nguyên không âm hữu hạn, mỗi bước giảm nên thuật toán dừng.

**Giới hạn:** 1-minimal theo deletion và local minimal theo magnitude không chứng minh globally minimal trong mọi representation. Dữ liệu có nhiều trường phụ thuộc có thể cần thay đồng thời hai trường mới tìm được phản ví dụ đơn giản hơn.

### Kiểm independently

Để test ddmin:
- Chạy F trên input cuối.
- Kiểm V trên input cuối.
- Thử xóa **từng phần tử một** bằng một hàm khác với logic phân chunk.
- Kiểm output luôn là subsequence của input gốc đối với deletion-only.
- Kiểm value shrinker không làm tăng magnitude.
- Thử n=1, n=2, input nhiều giá trị lặp, input invalid và input không fail.

Mã kiểm thêm `deletionOneMinimal` và một expected exact canonical [-1] cho họ bug đã biết.

## 15. Kết quả đối chiếu độc lập trước khi viết bài

Một mô hình kiểm thử thuật toán tách khỏi trình bày Java đã được thực hiện:
- **17.000** mảng có cấu trúc/random được đối chiếu Kadane với brute O(n²) khi nonempty.
- **3.500** mảng toàn âm được thu nhỏ, tất cả tới [-1] và vẫn fail.
- **19.000** mảng sorted đối chiếu lowerBound với linear scan.
- **20.000** bài stable three-way partition có tổng **895.062 item** được đối chiếu với oracle ba lượt theo class.

Các phép kiểm đúng trên những case đã chạy; trong quá trình dựng oracle partition, một lỗi dùng nhầm **giá trị item làm class index** đã được sửa trong mô hình kiểm, sau đó test mới PASS. Điều này nhắc lại rằng **test harness cũng phải được kiểm thử**.

Đây là kết quả **QA thực nghiệm hữu hạn**, không thay thế chứng minh tổng quát của thuật toán. Không suy “đã chạy hàng chục nghìn test” thành “chắc chắn đúng mọi input”.

## 16. Kiểm thử có biến hình và nhiều oracle

Khi output khó biết chính xác:
- Với sorting, kết hợp sortedness, permutation, idempotence và stability khi cần.
- Với graph, kiểm renaming invariance, bất đẳng thức theo cạnh, tính hợp lệ của path và so solver chậm trên graph nhỏ.
- Với matrix, kiểm `(Aᵀ)ᵀ=A` và `A·I=A`, nhưng không áp exact floating bitwise khi thay đổi thứ tự cộng có rounding.
- Với streaming, chia cùng input thành các chunk tùy ý; output cuối phải đúng theo contract và không phụ thuộc chunk boundaries.
- Với data structure có update/query, dùng một bản mảng/map đơn giản làm oracle trên lịch sử nhỏ.

**Không dùng oracle quá giống implementation.** Nếu hai thuật toán cùng áp một công thức sai cho interval bounds, differential testing có thể báo PASS dù cả hai sai. Tăng tính độc lập bằng brute/exhaustive enumeration, property thêm và một vài ví dụ tính tay.

## 17. Thu nhỏ lỗi flaky và lỗi tài nguyên

Nếu bug chỉ xuất hiện khi chạy song song:
- Một candidate có thể fail 10% số lần, pass 90%.
- Shrinker có thể bỏ dữ liệu đến mức không còn tạo đủ thread.
- Một timeout trên máy quá tải không chắc do thuật toán.
- Cùng seed không kiểm soát task scheduling.

Nên:
1. Cố định mức concurrency, kích thước tối thiểu và môi trường.
2. Chạy lặp nhiều lần để đo khả năng tái hiện.
3. Ghi failure signature riêng cho race/timeout/OOM.
4. Có timeout và budget shrink rõ ràng.
5. Không kết luận 1-minimal dựa vào một predicate không ổn định.

Với lỗi time/memory, phản ví dụ nhỏ nhất có thể vẫn rất lớn vì cần vượt một ngưỡng tài nguyên. Không ép mọi bug xuống input một phần tử.

## 18. CI và regression tests

Một workflow thực tế:
1. CI chạy deterministic seed suite.
2. Một case fail: ghi seed, caseId, input, expected, actual.
3. Xác minh validity và oracle.
4. Shrink trong một budget.
5. Chạy lại shrunk input với trạng thái sạch.
6. Lưu một regression test cố định, kèm input gốc nếu có ý nghĩa.
7. Sửa implementation.
8. Chạy cả regression, random suite và stress suite.
9. Theo dõi lỗi tái phát.

Ví dụ regression cho Kadane nonempty:

~~~java
// Snippet in a test class with kadaneNonempty defined.
int[] regression = {-1};
if (kadaneNonempty(regression) != -1L) {
    throw new AssertionError(
            "Nonempty subarray must not choose empty");
}
~~~

Đây là **mảnh code minh họa**, không phải một Java class độc lập. File Java đầy đủ ở mục 13.

Khi thay đổi generator, cần giữ một tập **regression input literal** không phụ thuộc cách PRNG sinh input sau này.

## 19. Các lỗi phổ biến

1. Sinh dữ liệu random nhưng không ghi seed và caseId.
2. Chỉ lưu seed mà không lưu input thực tế khi bug xuất hiện.
3. Một PRNG dùng liên tục bị thay thứ tự rút random khiến testcase biến đổi.
4. Sinh binary-search input chưa sorted.
5. Sinh đồ thị/matrix ngoài tiền điều kiện.
6. Sinh dãy lệnh không hợp lệ và gọi exception là bug.
7. Chỉ sinh random rộng, không chủ động có all-negative, duplicates, extremes.
8. Không test n=0,1 và các ngưỡng.
9. Cho oracle brute O(n²) chạy n rất lớn rồi timeout do chính test.
10. Oracle dùng lại recurrence sai của implementation.
11. Test harness dùng giá trị item làm chỉ số class.
12. Kết luận algorithm sai trước khi kiểm oracle/generator.
13. Chỉ kiểm sort sorted mà không kiểm permutation.
14. Không giữ occurrence ID khi test stability.
15. Cho một metamorphic property yếu đủ để chứng minh correctness.
16. Shrink thành input rỗng dù API cần nonempty.
17. Shrink connected graph mất liên thông.
18. Shrink A·B làm lệch inner dimensions.
19. Cắt một surrogate pair làm chuỗi invalid.
20. Shrink stateful operation sequence làm remove trước insert.
21. Candidate mutation làm thay đổi original input trước khi quyết định accept.
22. Không reset state giữa các lời gọi predicate.
23. Dùng exception bất kỳ làm F, shrink chuyển sang bug khác.
24. Dùng một timeout flaky làm tiêu chí deterministic.
25. Không giới hạn số lần F, shrink tốn tài nguyên.
26. Không dùng measure giảm đơn điệu, shrinker lặp vô hạn.
27. Dùng Math.abs(int) với Integer.MIN_VALUE.
28. Tưởng ddmin luôn tìm global minimum.
29. Tưởng 1-minimal theo deletion là tối ưu theo mọi phép biến đổi.
30. Không shrink giá trị sau khi đã giảm chiều dài.
31. Không lưu regression test sau khi shrink.
32. Sửa bug rồi không chạy lại input gốc.
33. Dùng `assert` Java nhưng không bật `-ea`.
34. So exact outputs của hai randomized algorithms có phân phối đúng nhưng RNG khác nhau.
35. So floating point bitwise dù contract cho sai số.
36. Chỉ có branch coverage, không có oracle chính xác.
37. Xem test pass nhiều lần là chứng minh toán học.
38. Chạy benchmark trước warm-up rồi xem là thuộc tính correctness.
39. Không phân biệt lỗi thuật toán với lỗi CI/infrastructure.
40. Cho seed tự quyết định scheduler/network/file system.
41. Không lưu generator version hoặc failure signature.
42. Không kiểm chính generator bằng invariants.
43. Không phân biệt false positive của test harness với counterexample thật.
44. Thu nhỏ bug concurrency xuống input không còn đủ task.
45. Báo cáo “minimal toàn cục” chỉ vì thử hết budget.

## 20. Bài tập

**Bài 1:** Sinh các mảng toàn âm độ dài 1..20 và tìm bug Kadane empty/nonempty. Viết đúng oracle brute.

**Bài 2:** Dùng ddmin cho [-8,−3,−5], tìm candidate giảm được và kiểm invalid [].

**Bài 3:** Giảm giá trị [−5] bằng 0,−1,−2, giải thích vì sao [-1] là ví dụ tốt.

**Bài 4:** Viết caseSeed từ master/id và phát lại case 100 mà không cần chạy 99 ca trước.

**Bài 5:** Viết kiểm invariant cho mode sorted/reverse/all-equal/all-negative của generator.

**Bài 6:** Sinh sorted arrays với duplicate, kiểm lowerBound bằng linear scan.

**Bài 7:** Sinh stable three-way partition, lưu original indices và so với ba lượt lọc.

**Bài 8:** Cố ý viết counts[a[i]] thay counts[classOf(a[i])] và giải thích lỗi harness.

**Bài 9:** Shrink một graph có source/target nhưng vẫn giữ reachability.

**Bài 10:** Shrink A(m×p)·B(p×n) bằng cách xóa đồng thời cột A và hàng B.

**Bài 11:** Thu nhỏ JSON bằng AST node chứ không xóa byte tùy ý.

**Bài 12:** Thu nhỏ chuỗi emoji theo Unicode code point, kiểm surrogate pair.

**Bài 13:** Thu nhỏ một lịch sử insert/delete/query mà vẫn giữ dependency.

**Bài 14:** Giải thích vì sao một race test fail 1/10 lần không thích hợp cho ddmin deterministic.

**Bài 15:** Phân biệt 1-minimal dưới phép xóa với global shortest counterexample.

**Bài 16:** Viết property cho range sum và phản ví dụ của một implementation luôn trả 0.

**Bài 17:** Tạo một metamorphic test cho matrix transpose hai lần.

**Bài 18:** Đo số lần oracle khi shrink với và không có cache, giới hạn budget.

**Bài 19:** Biến phản ví dụ [-1] thành regression test không phụ thuộc seed.

**Bài 20:** Thiết kế bộ small oracle tests, medium randomized tests và large stress tests cho một thuật toán bạn biết.

## 21. Checklist trước khi đưa generator/shrinker vào dự án

- Input hợp lệ theo đúng hợp đồng?
- Có oracle độc lập hoặc đủ properties mạnh?
- Có seed, caseId, mode, generator version và input literal?
- Tái lập được một test mà không chạy test trước?
- Có mode empty/singleton/duplicate/sorted/reverse/all-negative/extrema?
- Có kiểm generator bằng invariant?
- Có tách validity và failure predicate?
- Có giữ cùng failure signature?
- Có kiểm shrink candidate hợp lệ trước oracle?
- Có giảm cấu trúc rồi giảm giá trị khi phù hợp?
- Có measure giảm nghiêm ngặt để bảo đảm dừng?
- Có dùng Math.abs((long)x) cho int extrema?
- Có giới hạn ngân sách F và xử lý flaky/timeout?
- Có kiểm 1-minimality độc lập, không tuyên bố global?
- Có reset state trước mỗi test candidate?
- Có lưu regression nhỏ và input gốc?
- Có giữ ràng buộc giữa các trường của graph/matrix/sequence?
- Có phân biệt correctness với hiệu năng và race tests?
- Có ghi expected, actual và nguyên nhân chẩn đoán?
- Có chạy lại toàn suite sau khi sửa bug?

**Kết luận:** kiểm thử thuật toán không chỉ là rút nhiều số ngẫu nhiên. Cần **generator có seed và mode đúng phạm vi lỗi**, oracle/property độc lập, validity rõ ràng và khả năng tái lập từng case. Khi phát hiện sai, **ddmin** xóa phần input thừa, **value shrinking** làm giá trị dễ hiểu hơn, và mọi bước phải giữ đúng input hợp lệ cùng failure cần nghiên cứu. Kết quả thường là **1-minimal hoặc local minimum** theo các phép biến đổi, không phải globally minimal. Phản ví dụ Kadane nonempty `[-1]` cho thấy vì sao một input đơn giản có giá trị học tập và regression cao hơn một log random dài.