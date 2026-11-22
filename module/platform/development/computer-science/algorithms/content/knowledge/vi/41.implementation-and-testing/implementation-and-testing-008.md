# Kiểm thử trường hợp rỗng, nhỏ nhất, lớn nhất và phần tử trùng

## 1. Mục tiêu của kiểm thử biên

Một thuật toán có thể vượt hàng trăm dữ liệu ngẫu nhiên mà vẫn sai khi nhận **mảng rỗng**, **đúng một phần tử**, **giá trị bằng giới hạn kiểu số**, **độ dài chạm Nmax**, hoặc **nhiều phần tử có cùng khóa**. Đây là các điểm chuyển trạng thái của điều kiện vòng lặp, chỉ số mảng, phép so sánh và số lần xuất hiện.

**Boundary-value testing** tìm lỗi tại các ranh giới có khả năng thay đổi hành vi. **Equivalence partitioning** chia miền input thành nhóm có đặc điểm giống nhau; ta chọn vài đại diện rồi đặc biệt kiểm tra những giá trị ở sát mép. Hai kỹ thuật này cần phối hợp, chứ không chỉ ném thêm số random.

Bài sử dụng các thuật toán trên **mảng int đã sắp tăng không giảm** để minh họa:

- `lowerBound(A,x)`: chỉ số đầu tiên có A[i]≥x; nếu không có trả n.
- `upperBound(A,x)`: chỉ số đầu tiên có A[i]>x; nếu không có trả n.
- `countEqual(A,x)`: số occurrence của x, bằng upperBound−lowerBound.
- `uniqueSorted(A)`: các khóa phân biệt theo thứ tự tăng.
- `intersectDistinct(A,B)`: giao tập khóa của hai mảng sorted, không lặp.

Các ví dụ Java 17 không cần thư viện ngoài JDK. Phần test dùng oracle khác thuật toán gốc, vét cạn dãy nhỏ, kiểm ngẫu nhiên bằng seed cố định, kiểm hợp đồng null/unsorted và stress n=200.000.

## 2. Các trục biên phải tách biệt

Có ít nhất bốn trục độc lập:

**Rỗng:** số phần tử n=0. Mảng rỗng `new int[0]` hợp lệ có thể khác hoàn toàn `null`; không nên gộp hai loại khi thiết kế test.

**Kích thước nhỏ nhất:** thường n=1 hoặc n=2 nếu đề cấm rỗng; các điều kiện `i+1<n`, đoạn [0,n), điểm đầu và cuối có thể trở nên đặc biệt.

**Kích thước lớn nhất:** n=Nmax theo bài toán, có thể tạo áp lực độ phức tạp, bộ nhớ, stack và thời gian. Nmax không nhất thiết là 200.000 hay Integer.MAX_VALUE.

**Giá trị và multiplicity:** `Integer.MIN_VALUE`/`Integer.MAX_VALUE` kiểm overflow so sánh; các giá trị âm, 0 và nhiều duplicate kiểm ngữ nghĩa set/bag và vòng lặp tiến con trỏ.

Một ca n=200.000 chỉ chứa 0 thử tải kích thước nhưng không thử value extremes. Một ca gồm hai khóa MIN/MAX thử value extremes nhưng không thử tải kích thước. Vì vậy cần cả hai.

## 3. Hợp đồng hợp lệ và không hợp lệ

Trước khi kiểm bất kỳ output nào, mô tả input contract:

| Thuộc tính | Hợp đồng của ví dụ | Expected |
|---|---|---|
| Dữ liệu | Mảng int tăng không giảm | Duplicate hợp lệ |
| Mảng rỗng | Hợp lệ | Bound 0; unique và giao trả [] |
| Null | Không hợp lệ | NullPointerException |
| Input unsorted | Vi phạm precondition | Validator riêng từ chối |
| Tìm x không tồn tại | Hợp lệ | Trả vị trí chèn, không đọc A[n] |
| Kiểu kết quả giao | Set distinct | Mỗi khóa chỉ một lần |
| Side effect | Hàm không mutate input | Input sau gọi giống trước |
| Index bound | Miền kết quả [0,n] | n có thể là đáp án |
| Lỗi kiểm thử | AssertionError hoặc ngoại lệ kỳ vọng | Không in PASS khi test fail |

Một hàm binary search O(log n) có thể **giả định sortedness** để tránh phải kiểm toàn mảng O(n) trước mỗi lần tìm kiếm. Đối với input từ bên ngoài chưa tin cậy, dùng một bước `requireSorted` O(n) độc lập trước khi gọi nhiều truy vấn.

Với API khác, n=0 có thể không hợp lệ. Khi ấy test n=0 phải kiểm **đúng cách báo lỗi**, không tự ép mọi API chấp nhận rỗng.

## 4. Mảng rỗng, null và một phần tử

Trong Java:

```java
int[] empty = new int[0]; // độ dài 0
int[] missing = null;     // không có mảng
```

Một API trả tập giá trị có thể trả [] khi input empty, nhưng `min(empty)` cần một chính sách rõ vì không có giá trị min. Một API truy vấn graph không có đỉnh không thể cho phép start=0 là đỉnh hợp lệ.

Đối với lower/upper bound, vòng while có điều kiện `lo<hi` và hi=n. Với n=0, điều kiện sai ngay, trả 0 an toàn. Với n=1 và A=[5]:

| Target | Lower | Upper |
|---:|---:|---:|
| 4 | 0 | 0 |
| 5 | 0 | 1 |
| 6 | 1 | 1 |

Nếu chỉ test n=1 với x=5, có thể bỏ lỗi khi query nằm bên trái hoặc bên phải giá trị duy nhất. Nếu chỉ test n=0, có thể bỏ lỗi điều kiện mid trên n=1. Cần cả hai.

**Lỗi cơ bản cần phát hiện:**

```java
int first = a[0];         // lỗi nếu n=0
int last = a[a.length-1]; // lỗi nếu n=0
```

Phương án sửa phụ thuộc hợp đồng: trả tập rỗng, dùng Optional, hay ném ngoại lệ, không có một sentinel 0 đúng cho mọi loại bài.

## 5. Biên chỉ số và đoạn nửa mở

Với dãy có n phần tử, truy cập từng phần tử có index từ 0 đến n−1. Còn đoạn nửa mở [l,r) có điều kiện **0≤l≤r≤n**:

- [0,0), [n,n): đoạn rỗng hợp lệ.
- [0,n): toàn bộ mảng.
- [n−1,n): phần tử cuối nếu n>0.
- [−1,0), [0,n+1), [3,2): không hợp lệ.

Nếu một hàm trả **vị trí chèn** trong [0,n], kết quả n là hợp lệ nhưng không được dùng làm `A[n]`. Lỗi off-by-one thường phát sinh do nhầm [l,r] với [l,r) hoặc do viết `i<=n` trong vòng duyệt phần tử.

Khi kiểm lời giải, so expected **chỉ số chính xác**; không chỉ kiểm vị trí trả về có giá trị bằng target, bởi lowerBound còn đòi **vị trí đầu tiên**.

## 6. Giá trị nhỏ nhất/lớn nhất và overflow

Trong Java, int có giới hạn từ −2³¹ đến 2³¹−1. Nhiều comparator sai khi dùng phép trừ:

```java
int wrong = a - b;              // có thể overflow
int order = Integer.compare(a,b);
```

Ví dụ a=Integer.MIN_VALUE, b=Integer.MAX_VALUE; phép trừ có thể tràn và sai dấu. Các test số nhỏ không phát hiện được.

Tương tự, tránh midpoint `(lo+hi)/2` nếu lo+hi có thể vượt int:

```java
int mid = lo + (hi - lo) / 2;
```

Với 0≤lo≤hi≤n, phép tính này không cộng trực tiếp hai chỉ số có độ lớn lớn.

Nếu bài cần cộng nhiều int, chuyển sang long **trước khi cộng**, không phải sau:

```java
long sum = 0L;
for (int value : a) sum += value;
long pair = (long) a[0] + a[1];
```

`long pair=a[0]+a[1]` vẫn tính phần cộng bằng int trước khi chuyển kiểu. Test ở giá trị cực trị có thể phân biệt hai trường hợp.

### 6.1. Hai cận lớn nhất độc lập

**Kích thước lớn** tìm lỗi O(n²), OOM, stack overflow, dung lượng output. **Giá trị lớn** tìm lỗi tràn số và sentinel. Tạo cả ca dài toàn duplicate lẫn ca rất ngắn chứa MIN/MAX. Không thử cấp phát mảng vượt tài nguyên chỉ để chứng minh giới hạn hệ thống; test validation của Nmax ở lớp API riêng.

## 7. Phần tử trùng: set, bag, stability và thứ tự

Một khóa có thể xuất hiện 0,1,2 hoặc nhiều lần. Tùy toán tử:

- Set: [2,2,2] có một khóa distinct 2.
- Multiset/bag: [2,2,2] có ba occurrence.
- Binary search bất kỳ: với [1,2,2,2,5], chỉ số 1,2,3 đều là vị trí có giá trị 2; nhưng **lowerBound phải trả 1** và upperBound phải trả 4.
- Sorting stability: nếu nhiều bản ghi cùng key nhưng payload/ID khác nhau, có thể cần giữ thứ tự gốc.
- Inner join: hai occurrence trái và ba occurrence phải tạo **sáu cặp**; giao distinct chỉ ghi một khóa.

Các nhóm test trùng điển hình:

```text
[]                   rỗng
[7]                  một phần tử
[7,7]                hai giá trị bằng nhau
[7,7,7,7]            tất cả bằng nhau
[1,1,2,3]            duplicate ở đầu
[1,2,3,3]            duplicate ở cuối
[1,2,2,3,3,4]        nhiều nhóm trùng
[MIN,MIN,0,MAX,MAX]  trùng ở cực trị int
```

Một lỗi hai con trỏ là khi head bằng nhau mà không tăng chỉ số, gây vòng không dừng; lỗi khác là tăng một con trỏ nhưng vẫn ghi nhiều lần trái hợp đồng distinct.

## 8. Binary search với lowerBound và upperBound

Cho A tăng không giảm, định nghĩa:

- lowerBound(A,x): i nhỏ nhất thỏa A[i]≥x hoặc n nếu không có.
- upperBound(A,x): i nhỏ nhất thỏa A[i]>x hoặc n nếu không có.
- countEqual(A,x)=upperBound−lowerBound.

Pseudocode lowerBound:

```text
lo=0; hi=n
while lo<hi:
    mid=lo+(hi-lo)/2
    if A[mid]<x: lo=mid+1
    else:        hi=mid
return lo
```

UpperBound đổi điều kiện thành `A[mid]<=x`. Đặc biệt, nếu tất cả các phần tử đều nhỏ hơn target, cả lower và upper sẽ trả n.

**Bất biến lowerBound:** mọi chỉ số j<lo có A[j]<x; mọi j≥hi có A[j]≥x. Khi A[mid]<x, toàn bộ prefix tới mid đều <x nên lo=mid+1 đúng. Nếu A[mid]≥x, toàn bộ suffix từ mid đều ≥x nên hi=mid đúng. Khoảng tìm kiếm thu hẹp mỗi lần; khi lo=hi ta nhận chỉ số đầu tiên ≥x.

**Complexity:** thời gian O(log(n+1)), bộ nhớ O(1). Hàm không tự kiểm sortedness O(n) trong mỗi query, vì làm thế phá cam kết O(log n).

### 8.1. Mẫu boundary cụ thể

Với A=[1,2,2,2,5], test x=0,1,2,3,5,6:

| x | lower | upper | count |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 0 | 1 | 1 |
| 2 | 1 | 4 | 3 |
| 3 | 4 | 4 | 0 |
| 5 | 4 | 5 | 1 |
| 6 | 5 | 5 | 0 |

Nếu test chỉ dùng target đang tồn tại, bỏ qua 0,3,6 thì một số lỗi vị trí chèn có thể không bị bắt.

## 9. Loại duplicate trong dãy đã sort

Vì các giá trị bằng nhau nằm cạnh nhau, hàm distinct có thể quét một lượt:

```text
output=[]
for value in A:
    if output rỗng hoặc output.last!=value:
        output.append(value)
return output
```

**Bất biến:** sau prefix A[0..i), output chứa đúng các giá trị phân biệt của prefix, theo thứ tự tăng và không lặp. Nếu giá trị tiếp theo bằng output cuối, bỏ là đúng; nếu khác, thêm một giá trị mới.

Thời gian O(n), bộ nhớ output O(d) với d là số khóa distinct. Empty cho []; singleton giữ nguyên; mọi giá trị giống nhau cho mảng một phần tử.

Ba thuộc tính quan trọng:

1. **Idempotence:** D(D(A))=D(A).
2. **Conservation of values:** tập giá trị của D(A) bằng tập giá trị của A.
3. **Strict order:** các phần tử liền nhau trong D(A) tăng nghiêm ngặt.

Nếu hàm có hợp đồng không sửa input, test phải clone trước khi gọi và đối chiếu lại sau.

## 10. Giao distinct hai dãy sorted

Giữ con trỏ i trong A, j trong B. Khi A[i]<B[j], A[i] không thể có ở phần B chưa đọc vì mọi giá trị tiếp theo ≥B[j]; tiến i. Khi A[i]>B[j], tiến j. Khi bằng, đó là khóa chung: chỉ thêm nếu khác giá trị vừa xuất, rồi tiến cả i và j.

```text
i=0; j=0; output=[]
while i<len(A) and j<len(B):
    if A[i]<B[j]: i++
    else if A[i]>B[j]: j++
    else:
        if output rỗng hoặc output.last!=A[i]:
            output.append(A[i])
        i++;j++
return output
```

Vòng lặp luôn tăng một con trỏ, nên kết thúc sau O(n+m) bước. Output tối đa min(n,m) phần tử và sắp tăng nghiêm ngặt.

**Chứng minh đúng:** bất biến mọi khóa nhỏ hơn min(headA,headB) đã được quyết định đúng. Khi a<b, không có đối tác a phía B ở phần sau; khi bằng nhau, khóa nằm trong cả hai tập. Duplicate được kiểm bằng output cuối, nên xuất đúng một lần.

**Cảnh báo:** đây là giao theo **set semantics**. Với INTERSECT ALL, số lần xuất khóa x là min(countA(x),countB(x)), không phải một.

## 11. Oracle độc lập

Một test không được lấy **chính hàm đang thử** làm công thức tạo expected. Nếu cả hai lần gọi dùng cùng một lỗi, phép so có thể cùng sai mà vẫn PASS.

Các oracle của chương trình Java là:

- LowerBound: quét từ đầu để tìm vị trí đầu tiên ≥x.
- UpperBound: quét từ đầu để tìm vị trí đầu tiên >x.
- Count: đếm trực tiếp mọi occurrence bằng vòng for.
- Unique: thêm các giá trị vào `TreeSet<Integer>` rồi xuất theo thứ tự.
- Intersection: hai `TreeSet` và phép `retainAll`, khác hoàn toàn hai con trỏ.
- No mutation: clone input rồi so `Arrays.equals` sau khi chạy.

Các oracle này có thể tốn O(n) hoặc O(n log n); điều đó hợp lý trong test vì dữ liệu nhỏ và logic độc lập quan trọng hơn tốc độ oracle.

### 11.1. Metamorphic testing

Ngoài oracle, ta còn kiểm quan hệ giữa các input/output:

- D(D(A))=D(A) (idempotent).
- I(A,B)=I(B,A) (giao hoán).
- I(A,A)=D(A).
- I(A,[])=[].
- LowerBound≤UpperBound và đều ở [0,n].
- Nếu chèn thêm một occurrence của khóa đã có, distinct không đổi nhưng count của khóa tăng 1.
- Nếu dịch tất cả giá trị và target cùng hằng số mà không overflow, vị trí bound không đổi.

Thuộc tính biến hình (**metamorphic**) giúp mở rộng kiểm thử nhưng không thay oracle độc lập hay những case có expected cụ thể.

## 12. Exhaustive testing miền nhỏ

Chọn domain {−1,0,1}. Với mảng độ dài n có 3ⁿ dãy raw. Nếu xét n=0..6, tổng số là:

**1+3+9+27+81+243+729 = 1.093 dãy**.

Sinh từng dãy theo chữ số cơ số 3, sort rồi kiểm lower/upper, count và unique. Dù nhiều dãy raw sau sort trở thành giống nhau, không gây hại cho kiểm thử.

Với hai input của phép giao, dùng độ dài 0..4 để chi phí vừa phải. Số dãy là:

**1+3+9+27+81=121**.

Test mọi cặp cho **121²=14.641 cặp**. Mỗi cặp kiểm TreeSet oracle, giao hoán, giao với chính nó và input không bị thay đổi.

**Tại sao không vét cạn tới n=100?** Vì số ca tăng theo 3ⁿ; nên vét cạn nhỏ để kiểm các pattern tinh tế rồi thêm random/stress trên miền lớn hơn.

## 13. Random testing có seed

Chương trình sinh **4.000 cặp mảng**, mỗi bên dài 0..80. Giá trị lấy từ domain có số âm, 0 lặp nhiều lần, ±1 và cả Integer.MIN_VALUE/MAX_VALUE. Sau `Arrays.sort`, các input thỏa tiền điều kiện sorted.

`Random(542L)` bảo đảm khi chạy lại cùng code/seed thì tạo cùng chuỗi ca. Một lỗi random phải được lưu lại thành **regression test** với seed, trial index và input cụ thể. Có thể giảm dãy lỗi bằng cách xóa phần tử không cần thiết hoặc giảm độ lớn giá trị tới khi còn phản ví dụ nhỏ.

Không thể nói 4.000 ca PASS chứng minh mọi input đều đúng. Khả năng phát hiện lỗi phụ thuộc cấu trúc generator; đừng chỉ lấy số random dương khác nhau mà bỏ qua duplicate, âm và cực trị.

## 14. Stress input lớn

Bản demo dùng n=200.000, gồm 100.000 phần tử MIN, 99.999 số 0 và một MAX. Expected:

```text
lowerBound(MIN)=0
upperBound(MIN)=100000
lowerBound(0)=100000
upperBound(0)=199999
countEqual(MAX)=1
uniqueSorted length=3
```

Nó kiểm cùng lúc số lượng lớn, nhóm duplicate khổng lồ, và hai giá trị cực trị. Tuy nhiên n=200.000 chỉ là **mức stress minh họa**, không phải giới hạn của mọi bài toán hay của Java.

Để xác nhận hiệu năng, nên thử nhiều kích thước theo cấp số nhân trong ngân sách CPU/RAM, warm-up JVM, tách thời gian oracle khỏi thuật toán, theo dõi memory/GC, và đối chiếu với phân tích O(log n), O(n), O(n+m) chứ không chỉ nhìn một lần đo.

## 15. Input sai hợp đồng và validation

Một API low-level có thể dựa vào precondition sorted để thực hiện binary search O(log n). Nếu muốn phòng input từ file/HTTP chưa kiểm, dùng `requireSorted` O(n) **một lần** trước chuỗi truy vấn.

- Null: `Objects.requireNonNull` ném NullPointerException.
- Rỗng: input hợp lệ với các thuật toán mẫu.
- Dữ liệu giảm thứ tự: `requireSorted` ném IllegalArgumentException.
- Index vượt miền: các API access riêng cần kiểm và báo lỗi.
- Kích thước vượt Nmax: nên kiểm trước khi cấp phát quá lớn.

Đừng tuyên bố hàm binary search O(log n) nếu lén quét toàn input O(n) ở mỗi query. Cũng không nên đặt expected cho input invalid mà hàm low-level **không** hứa tự kiểm.

### 15.1. Java assert có thể bị tắt

`assert expression;` của Java mặc định có thể không chạy nếu không bật `-ea`. Chương trình cuối bài dùng hàm `check` ném AssertionError rõ ràng và chạy được ngay bằng lệnh `java EdgeCaseAlgorithmTests`, không phụ thuộc cờ bổ sung.

## 16. Độ phức tạp và chiến lược kiểm thử

| Phép toán | Thời gian | Bộ nhớ thêm |
|---|---|---|
| lowerBound / upperBound | O(log(n+1)) | O(1) |
| countEqual | O(log(n+1)) | O(1) |
| uniqueSorted | O(n) | O(d) output |
| intersectDistinct | O(n+m) | O(min(n,m)) output |
| requireSorted | O(n) | O(1) |
| Oracle linear scan | O(n) mỗi query | O(1) |
| TreeSet oracle | O(n log n) tổng quát | O(d) |
| Exhaustive small | Theo số pattern | Input nhỏ |
| Stress | Theo thuật toán được test | RAM phù hợp |

Không lấy số ca PASS hay line coverage làm chứng minh tính đúng tuyệt đối. Phối hợp bất biến, oracle, ca biên, lỗi ngoại lệ và kiểm tải.

## 17. Những mẫu regression cần giữ

| Mã | Input | Expected |
|---|---|---|
| E0 | lowerBound([],7) | 0 |
| E1 | uniqueSorted([]) | [] |
| E2 | I([],[1,2]) | [] |
| S0 | lowerBound([5],4) | 0 |
| S1 | lowerBound([5],5) | 0 |
| S2 | lowerBound([5],6) | 1 |
| D0 | countEqual([2,2,2],2) | 3 |
| D1 | uniqueSorted([2,2,2]) | [2] |
| D2 | I([1,1,2,3,3],[1,2,2,3]) | [1,2,3] |
| V0 | lowerBound([MIN,MAX],MIN) | 0 |
| V1 | upperBound([MIN,MAX],MAX) | 2 |
| N0 | lowerBound([1,3,5],4) | 2 |
| N1 | lowerBound([1,3,5],6) | 3 |
| C0 | requireSorted([2,1]) | IllegalArgumentException |
| C1 | lowerBound(null,0) | NullPointerException |
| L0 | Input dài 200.000 | Bound và distinct đúng mục 14 |

Nếu một ca từng phát hiện bug, không xóa nó sau khi sửa; đưa thành regression fixture ổn định.



## 18. Java 17 tự chạy: kiểm thử dữ liệu biên

Lưu tệp `EdgeCaseAlgorithmTests.java` dưới đây. Chương trình dùng hàm `check` và `same` để ném AssertionError khi lỗi, vì thế **không phụ thuộc cờ `-ea`** của Java. Oracle trong test chủ động dùng thuật toán khác với code được kiểm.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.TreeSet;

public final class EdgeCaseAlgorithmTests {
    private EdgeCaseAlgorithmTests() {}

    // Precondition: sorted ascending (duplicates allowed).
    static int lowerBound(int[] a, int x) {
        Objects.requireNonNull(a, "a");
        int lo = 0, hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] < x) lo = mid + 1;
            else hi = mid;
        }
        return lo;
    }

    static int upperBound(int[] a, int x) {
        Objects.requireNonNull(a, "a");
        int lo = 0, hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] <= x) lo = mid + 1;
            else hi = mid;
        }
        return lo;
    }

    static int countEqual(int[] a, int x) {
        return upperBound(a, x) - lowerBound(a, x);
    }

    static int[] uniqueSorted(int[] a) {
        Objects.requireNonNull(a, "a");
        int[] out = new int[a.length];
        int size = 0;
        for (int value : a) {
            if (size == 0 || out[size - 1] != value) {
                out[size++] = value;
            }
        }
        return Arrays.copyOf(out, size);
    }

    static int[] intersectDistinct(int[] a, int[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        int[] out = new int[Math.min(a.length, b.length)];
        int i = 0, j = 0, size = 0;
        while (i < a.length && j < b.length) {
            if (a[i] < b[j]) i++;
            else if (a[i] > b[j]) j++;
            else {
                if (size == 0 || out[size - 1] != a[i]) {
                    out[size++] = a[i];
                }
                i++;
                j++;
            }
        }
        return Arrays.copyOf(out, size);
    }

    // Optional O(n) validator for untrusted input.
    static void requireSorted(int[] a) {
        Objects.requireNonNull(a, "a");
        for (int i = 1; i < a.length; i++) {
            if (a[i] < a[i - 1]) {
                throw new IllegalArgumentException(
                    "expected nondecreasing array");
            }
        }
    }

    // Independent linear scan oracles.
    static int linearLower(int[] a, int x) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] >= x) return i;
        }
        return a.length;
    }

    static int linearUpper(int[] a, int x) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] > x) return i;
        }
        return a.length;
    }

    static int linearCount(int[] a, int x) {
        int result = 0;
        for (int v : a) if (v == x) result++;
        return result;
    }

    static int[] toArray(TreeSet<Integer> set) {
        int[] result = new int[set.size()];
        int i = 0;
        for (int x : set) result[i++] = x;
        return result;
    }

    static int[] uniqueOracle(int[] a) {
        TreeSet<Integer> set = new TreeSet<>();
        for (int x : a) set.add(x);
        return toArray(set);
    }

    static int[] intersectionOracle(int[] a, int[] b) {
        TreeSet<Integer> left = new TreeSet<>();
        TreeSet<Integer> right = new TreeSet<>();
        for (int x : a) left.add(x);
        for (int x : b) right.add(x);
        left.retainAll(right);
        return toArray(left);
    }

    static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static void same(int[] actual, int[] expected, String why) {
        if (!Arrays.equals(actual, expected)) {
            throw new AssertionError(why
                + " actual=" + Arrays.toString(actual)
                + " expected=" + Arrays.toString(expected));
        }
    }

    static void expectException(
            Class<? extends Throwable> expected, Runnable task) {
        boolean found = false;
        try {
            task.run();
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                    "unexpected exception " + error);
            }
            found = true;
        }
        check(found, "missing exception " + expected.getName());
    }

    static void verifyArray(int[] a) {
        requireSorted(a);
        int[] original = a.clone();
        int[] unique = uniqueSorted(a);
        same(unique, uniqueOracle(a), "unique oracle");
        same(uniqueSorted(unique), unique, "unique idempotence");

        int[] queries = {
            Integer.MIN_VALUE, -101, -2, -1, 0, 1, 2, 101,
            Integer.MAX_VALUE
        };
        for (int x : queries) {
            int lo = lowerBound(a, x);
            int hi = upperBound(a, x);
            check(lo == linearLower(a, x),
                "lowerBound target=" + x);
            check(hi == linearUpper(a, x),
                "upperBound target=" + x);
            check(0 <= lo && lo <= hi && hi <= a.length,
                "bounds invariant");
            check(countEqual(a, x) == linearCount(a, x),
                "count target=" + x);
        }
        same(a, original, "mutated input array");
    }

    static void verifyPair(int[] a, int[] b) {
        requireSorted(a);
        requireSorted(b);
        int[] originalA = a.clone();
        int[] originalB = b.clone();
        int[] result = intersectDistinct(a, b);
        same(result, intersectionOracle(a, b),
            "intersection oracle");
        same(result, intersectDistinct(b, a),
            "intersection commutativity");
        same(intersectDistinct(a, a), uniqueSorted(a),
            "intersection with self");
        same(a, originalA, "modified first input");
        same(b, originalB, "modified second input");
    }

    static int pow3(int n) {
        int result = 1;
        for (int i = 0; i < n; i++) result *= 3;
        return result;
    }

    static int[] fromBase3(int n, int digits) {
        int[] a = new int[n];
        for (int i = 0; i < n; i++) {
            a[i] = digits % 3 - 1;
            digits /= 3;
        }
        Arrays.sort(a); // Only test generator sorts input.
        return a;
    }

    public static void main(String[] args) {
        int[] empty = {};
        verifyArray(empty);
        verifyPair(empty, empty);
        check(lowerBound(empty, 7) == 0
                && upperBound(empty, 7) == 0,
            "empty bound");
        System.out.println("Case empty: PASS");

        int[] single = {5};
        verifyArray(single);
        check(lowerBound(single, 4) == 0
                && lowerBound(single, 5) == 0
                && lowerBound(single, 6) == 1,
            "singleton");
        System.out.println("Case singleton: PASS");

        int[] duplicates = {-2, -2, 0, 0, 0, 3, 3};
        int[] partner = {-2, -2, 1, 3, 3};
        verifyArray(duplicates);
        verifyPair(duplicates, partner);
        same(intersectDistinct(duplicates, partner),
            new int[] {-2, 3}, "duplicate intersection");
        check(countEqual(duplicates, 0) == 3, "duplicate count");
        System.out.println("Case duplicates: PASS");

        int[] extremes = {
            Integer.MIN_VALUE, Integer.MIN_VALUE,
            0, Integer.MAX_VALUE, Integer.MAX_VALUE
        };
        verifyArray(extremes);
        check(lowerBound(extremes, Integer.MIN_VALUE) == 0
                && upperBound(extremes, Integer.MIN_VALUE) == 2
                && lowerBound(extremes, Integer.MAX_VALUE) == 3
                && upperBound(extremes, Integer.MAX_VALUE) == 5,
            "extreme int");
        System.out.println("Case integer extremes: PASS");

        expectException(NullPointerException.class,
            () -> lowerBound(null, 0));
        expectException(NullPointerException.class,
            () -> uniqueSorted(null));
        expectException(IllegalArgumentException.class,
            () -> requireSorted(new int[] {2, 1}));
        System.out.println("Null / unsorted contracts: PASS");

        int arrays = 0;
        for (int n = 0; n <= 6; n++) {
            for (int code = 0; code < pow3(n); code++) {
                verifyArray(fromBase3(n, code));
                arrays++;
            }
        }
        check(arrays == 1093, "exhaustive array count");
        System.out.println(
            "Exhaustive sorted arrays: " + arrays + " PASS");

        List<int[]> patterns = new ArrayList<>();
        for (int n = 0; n <= 4; n++) {
            for (int code = 0; code < pow3(n); code++) {
                patterns.add(fromBase3(n, code));
            }
        }
        long pairs = 0;
        for (int[] a : patterns) {
            for (int[] b : patterns) {
                verifyPair(a, b);
                pairs++;
            }
        }
        check(patterns.size() == 121 && pairs == 14641,
            "exhaustive pair count");
        System.out.println(
            "Exhaustive sorted pairs: " + pairs + " PASS");

        Random rng = new Random(542L);
        int[] domain = {
            Integer.MIN_VALUE, Integer.MIN_VALUE,
            -100, -1, -1, 0, 0, 0, 1, 1,
            100, Integer.MAX_VALUE, Integer.MAX_VALUE
        };
        for (int t = 0; t < 4000; t++) {
            int[] a = new int[rng.nextInt(81)];
            int[] b = new int[rng.nextInt(81)];
            for (int i = 0; i < a.length; i++) {
                a[i] = domain[rng.nextInt(domain.length)];
            }
            for (int i = 0; i < b.length; i++) {
                b[i] = domain[rng.nextInt(domain.length)];
            }
            Arrays.sort(a);
            Arrays.sort(b);
            verifyArray(a);
            verifyArray(b);
            verifyPair(a, b);
        }
        System.out.println("Random differential pairs: 4000 PASS");

        int[] big = new int[200_000];
        Arrays.fill(big, 0, 100_000, Integer.MIN_VALUE);
        Arrays.fill(big, 100_000, 199_999, 0);
        big[199_999] = Integer.MAX_VALUE;
        verifyArray(big);
        verifyPair(big, big);
        check(lowerBound(big, Integer.MIN_VALUE) == 0
                && upperBound(big, Integer.MIN_VALUE) == 100_000
                && lowerBound(big, 0) == 100_000
                && upperBound(big, 0) == 199_999
                && countEqual(big, Integer.MAX_VALUE) == 1
                && uniqueSorted(big).length == 3,
            "large duplicate input");
        System.out.println(
            "Large repeated input length 200000: PASS");
        System.out.println("All edge-case checks: PASS");
    }
}
```

### 18.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 EdgeCaseAlgorithmTests.java
java EdgeCaseAlgorithmTests
```

**Stdout khi tất cả ca vượt qua:**

```text
Case empty: PASS
Case singleton: PASS
Case duplicates: PASS
Case integer extremes: PASS
Null / unsorted contracts: PASS
Exhaustive sorted arrays: 1093 PASS
Exhaustive sorted pairs: 14641 PASS
Random differential pairs: 4000 PASS
Large repeated input length 200000: PASS
All edge-case checks: PASS
```

Nếu một ca sai, AssertionError hoặc ngoại lệ không kỳ vọng sẽ dừng chương trình trước dòng kết luận cuối. Đây là hành vi thích hợp trong CI.

### 18.2. Ý nghĩa từng nhóm test

**Case empty:** không truy cập phần tử đầu của mảng rỗng; lower/upper trả 0, unique/giao trả [].

**Case singleton:** bắt lỗi nhầm khi chỉ có một phần tử. Ba target trước, bằng và sau giá trị đầu vào cho ba vị trí/giá trị khác nhau.

**Case duplicates:** nhóm trùng ở cả hai luồng, đếm đúng ba occurrence của 0 nhưng giao distinct chỉ giữ khóa chung một lần.

**Case integer extremes:** xác nhận MIN_VALUE/MAX_VALUE không làm sai comparator, first/last bounds và khả năng đếm.

**Null / unsorted contracts:** rỗng hợp lệ, null bị từ chối, và validator báo lỗi khi có cặp giảm. Hàm lowerBound giữ O(log n) vì không quét toàn dãy ở mỗi query.

**Exhaustive arrays:** 1.093 dãy sorted sinh từ {−1,0,1}, kiểm bound/count với quét tuyến tính, unique với TreeSet, idempotence và no-mutation.

**Exhaustive pairs:** 14.641 cặp dãy ngắn, đối chiếu TreeSet intersection; kiểm giao hoán, self-intersection và mảng nguồn không đổi.

**Random:** 4.000 cặp mảng 0..80 phần tử, thiên về duplicate, số âm, 0 và hai giới hạn int; dùng cùng các oracle.

**Large repeated:** 200.000 phần tử gồm ba nhóm lớn, kiểm vị trí 0, 100.000, 199.999 và n qua các bound.

### 18.3. Không nhận số test PASS là chứng minh tuyệt đối

Đếm được 4.000 ca PASS không bảo đảm tất cả input đúng. Nó chỉ khẳng định những input đã kiểm phù hợp oracle trong phiên chạy đó. Hãy kết hợp:

- Chứng minh invariant của thuật toán.
- Vét cạn miền nhỏ.
- Random đa dạng có seed.
- Case biên thủ công có expected.
- Stress và benchmark trong ngân sách tài nguyên.
- Regression fixture cho mọi lỗi từng được tìm thấy.

Nếu chuyển sang JUnit 5, có thể dùng parameterized tests cho bảng ca ở mục 17 và thư viện property-based cho generator/shrinking; điều quan trọng là giữ **ngữ nghĩa hợp đồng và oracle độc lập**, không phải tên framework.

## 19. Lỗi kiểm thử phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách tránh |
|---|---|---|
| Chỉ test n≥10 | Không chạm rỗng/singleton | n=0/1/2 và Nmax |
| Coi null như empty | Che lỗi API | Hai loại case riêng |
| Chỉ test target có trong mảng | Bỏ vị trí chèn | Target trước min, giữa, sau max |
| Chỉ check giá trị tại index | Không bắt first occurrence | So exact lower/upper |
| Không test all-equal | Bỏ lỗi xử lý duplicate | [x,x,x,...] |
| Nhầm set với multiset | Count sai | Ghi rõ distinct hoặc bag |
| So số bằng a-b | Integer overflow | Integer.compare |
| Lấy midpoint bằng (lo+hi)/2 | Có thể overflow | lo+(hi-lo)/2 |
| Chuyển int sang long sau cộng | Overflow trước chuyển | Cast trước phép cộng |
| Dùng chính hàm đang test làm oracle | Hai lần cùng sai vẫn PASS | Linear scan/TreeSet |
| Không kiểm input mutation | Hàm làm hỏng nguồn | Clone và so |
| Sinh random chưa sorted | Vi phạm precondition | Sort dữ liệu trước gọi |
| Random chỉ có khóa dương khác nhau | Không có negative/duplicate/extreme | Biased domain |
| Random không seed | Lỗi khó tái lập | Lưu seed/trial/input |
| Xóa test sau khi sửa bug | Bug tái phát | Giữ regression case |
| Stress tới mức OOM runner | CI không ổn định | Ngân sách riêng |
| Chỉ một kích thước stress | Không chứng minh complexity | Benchmark nhiều n |
| Dùng Java assert nhưng không bật -ea | Assert không chạy | check hoặc JUnit |
| Catch tất cả rồi in PASS | Che exception thực | Chỉ bắt đúng loại kỳ vọng |
| Chỉ so output length | Giá trị/order có thể sai | Arrays.equals |
| Coi coverage 100% là đúng | Chưa có dữ liệu biên | Kết hợp oracle và boundary |
| Không tính tiền điều kiện | Test có kỳ vọng sai | Hợp đồng trước test |
| Benchmark gồm cả oracle | Đo hiệu năng nhầm | Tách thuật toán và test |

## 20. Bài tập có đáp án

**Bài 1.** lowerBound([],5) là gì? *Đáp án:* 0.

**Bài 2.** upperBound([],5)? *Đáp án:* 0.

**Bài 3.** uniqueSorted([])? *Đáp án:* [].

**Bài 4.** Giao [] và [1,2]? *Đáp án:* [].

**Bài 5.** lowerBound([7],6)? *Đáp án:* 0.

**Bài 6.** lowerBound([7],8)? *Đáp án:* 1.

**Bài 7.** upperBound([7],7)? *Đáp án:* 1.

**Bài 8.** countEqual([2,2,2],2)? *Đáp án:* 3.

**Bài 9.** lowerBound([1,2,2,2,5],2)? *Đáp án:* 1.

**Bài 10.** upperBound([1,2,2,2,5],2)? *Đáp án:* 4.

**Bài 11.** countEqual([1,2,2,2,5],2)? *Đáp án:* 3.

**Bài 12.** lowerBound([1,3,5],4)? *Đáp án:* 2.

**Bài 13.** lowerBound([1,3,5],6)? *Đáp án:* 3.

**Bài 14.** uniqueSorted([3,3,3])? *Đáp án:* [3].

**Bài 15.** Giao [1,1,2,3,3] và [1,2,2,3]? *Đáp án:* [1,2,3].

**Bài 16.** Tại sao cần test Integer.MIN_VALUE và MAX_VALUE? *Đáp án:* phát hiện comparator overflow và các sentinel sai.

**Bài 17.** Midpoint an toàn cho binary search? *Đáp án:* lo+(hi-lo)/2.

**Bài 18.** new int[0] có giống null không? *Đáp án:* không.

**Bài 19.** Nếu hợp đồng yêu cầu n≥1, test n=0 kỳ vọng gì? *Đáp án:* báo lỗi input phù hợp, không bắt buộc trả [].

**Bài 20.** D(D(A)) bằng gì? *Đáp án:* D(A).

**Bài 21.** I(A,B) và I(B,A) có bằng nhau theo set semantics? *Đáp án:* có.

**Bài 22.** I(A,A) bằng gì? *Đáp án:* D(A).

**Bài 23.** Oracle cho binary search? *Đáp án:* quét tuyến tính độc lập.

**Bài 24.** Oracle cho distinct và giao? *Đáp án:* TreeSet.

**Bài 25.** Domain ba giá trị, n=0..6 có bao nhiêu dãy? *Đáp án:* 1.093.

**Bài 26.** Domain ba giá trị, n=0..4 có bao nhiêu dãy? *Đáp án:* 121.

**Bài 27.** Tổng số cặp từ 121 dãy? *Đáp án:* 14.641.

**Bài 28.** Random seed có lợi gì? *Đáp án:* tái lập input để debug.

**Bài 29.** Random 4.000 ca PASS có chứng minh không còn lỗi? *Đáp án:* không.

**Bài 30.** Test n=200.000 có tương đương test MAX_VALUE không? *Đáp án:* không, một là kích thước, một là giá trị.

**Bài 31.** Vì sao cần so mảng nguồn trước/sau? *Đáp án:* phát hiện mutation ngoài hợp đồng.

**Bài 32.** Java assert mặc định có luôn chạy? *Đáp án:* không, nếu thiếu -ea.

**Bài 33.** Khi fuzz tìm ra lỗi, nên lưu gì? *Đáp án:* seed, trial, input phản ví dụ rồi shrink và thêm regression.

**Bài 34.** Vì sao duplicate khi inner join khác giao distinct? *Đáp án:* join xuất mọi cặp khớp, giao distinct chỉ một khóa.

**Bài 35.** Đồ thị một đỉnh, không cạnh, BFS từ đỉnh đó có thể thăm bao nhiêu? *Đáp án:* một.

**Bài 36.** Input rỗng được coi đã sorted không? *Đáp án:* theo thứ tự không giảm, nó không có cặp vi phạm; còn hợp lệ hay không phụ thuộc hợp đồng n.

## 21. Áp dụng sang các loại thuật toán khác

**Chuỗi:** chuỗi rỗng, một ký tự, tất cả ký tự giống nhau, pattern dài hơn text, pattern rỗng theo contract, Unicode normalization và surrogate pair. Java String.length() đếm UTF-16 code units, không luôn là số ký tự cảm nhận.

**Đồ thị:** 0/1 đỉnh, đỉnh cô lập, không cạnh, self-loop, cạnh song song, đồ thị đầy đủ có kiểm giới hạn, trọng số âm/0/lớn. Với Dijkstra, trọng số âm vi phạm tiền điều kiện; cần test rejection hoặc chọn thuật toán khác.

**Cây:** một nút, cây đường dài, cây sao, cây cân bằng, key trùng, truy vấn root/leaf và hai nút giống nhau. Cây đường dài dễ làm DFS đệ quy tràn stack dù cây cân bằng cùng n chạy tốt.

**DP:** n=0/1, base cases, không có nghiệm, nhiều nghiệm tối ưu, kết quả hợp lệ bằng 0, sentinel vô cùng, overflow khi cộng chi phí.

**Sắp xếp:** mảng rỗng, singleton, toàn bằng nhau, đã tăng, giảm hoàn toàn, số âm và cực trị; nếu yêu cầu stable, gắn ID cho các bản ghi key trùng rồi kiểm thứ tự.

**API:** offset 0, limit 0/1/max, trang cuối một phần tử, kết quả rỗng, duplicate ID, null, giá trị không hợp lệ, boundary timestamp.

Mọi lĩnh vực đều cần chốt hợp đồng trước khi kết luận một ca biên đúng hay sai.

## 22. Checklist hoàn thành QA

1. Phân biệt empty, null, min valid size và max valid size.
2. Kiểm n=0,1,2 và Nmax/Nmax−1 khi phù hợp.
3. Kiểm index 0,n−1,n,−1 theo semantics.
4. Kiểm MIN/MAX value, số âm, 0 và khóa không có.
5. Kiểm all-equal và duplicate ở đầu/giữa/cuối.
6. Có expected cụ thể cho first/last occurrence.
7. Dùng oracle độc lập, không tự xác nhận bằng cùng thuật toán.
8. Kiểm idempotence/giao hoán/no-mutation.
9. Vét cạn miền nhỏ và random có seed.
10. Lưu phản ví dụ khi phát hiện lỗi.
11. Test input invalid bằng đúng loại ngoại lệ hợp đồng.
12. Stress cỡ lớn trong giới hạn tài nguyên.
13. Không để oracle làm sai benchmark thuật toán.
14. Đảm bảo assertion thực sự chạy.
15. Giữ regression test sau khi sửa lỗi.
16. Không coi số case PASS là chứng minh toán học.
17. Đối chiếu với chứng minh bất biến và độ phức tạp.
18. Kiểm rõ set, multiset và stability khi có duplicate.

**Kết luận:** kiểm thử trường hợp rỗng, nhỏ nhất, lớn nhất và phần tử trùng giúp phát hiện những sai sót khó nhìn thấy ở dữ liệu thông thường. Cách làm hiệu quả là kết hợp **hợp đồng rõ**, **bảng ca biên**, **oracle độc lập**, **vét cạn input nhỏ**, **random có seed** và **stress có ngân sách**. Không chỉ đo có crash hay không: cần kiểm đúng kết quả, bất biến, ngoại lệ và side effect.
