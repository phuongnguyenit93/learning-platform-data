# Mô hình chi phí và phép toán cơ bản

**Mục tiêu:** Biết một phát biểu như “thuật toán mất O(n) thời gian” đang dựa trên giả thiết nào; xác định phép toán cơ bản cần đếm; lập được biểu thức chi phí từ các vòng lặp, nhánh điều kiện và lời gọi hàm; phân biệt số phép toán lý thuyết với thời gian thực tế, đặc biệt khi dùng Java.

Trong phân tích thuật toán, “nhanh” hay “chậm” cần có **đơn vị đo và mô hình tính chi phí**. Hai chương trình cùng thực hiện một chức năng có thể sử dụng số phép so sánh, lần truy cập bộ nhớ, byte đọc/ghi hoặc phép toán trên số lớn rất khác nhau. Mô hình chi phí giúp ta đặt ra những giả thiết rõ ràng để so sánh thuật toán một cách có cơ sở.

## 1. Mô hình chi phí là gì?

**Mô hình chi phí (cost model)** quy định những thao tác được tính, chi phí của từng thao tác và cách cộng các chi phí khi thuật toán chạy. Đặt `x` là một đầu vào hợp lệ; có thể mô tả tổng chi phí:

`C(x) = Σ_i c_i · N_i(x)`

Trong đó:

- `N_i(x)` là số lần thuật toán thực hiện loại thao tác `i` trên đầu vào `x`, chẳng hạn phép so sánh, phép cộng, phép đọc phần tử, hay truy cập một khối đĩa.
- `c_i` là chi phí mỗi lần thao tác loại `i` theo mô hình đang dùng. Khi phân tích số phép toán cơ bản, thường coi một số `c_i` là hằng số dương.
- `C(x)` phụ thuộc vào **giá trị và cấu trúc cụ thể của đầu vào**, không chỉ vào độ dài của nó; ví dụ tìm kiếm tuyến tính có thể dừng ở phần tử đầu tiên hoặc phải duyệt hết.

Sau khi xác định cách đo kích thước `|x| = n`, ta có thể xét chi phí theo `n`. Để chỉ ra **chi phí xấu nhất**, dùng:

`T_worst(n) = max { C(x) : x hợp lệ và |x| = n }`.

Đây là định nghĩa trong phạm vi các đầu vào hợp lệ có cùng kích thước. Nếu tập đầu vào ở kích thước `n` không có phần tử, phải điều chỉnh miền xét; trong các bài toán hữu hạn quen thuộc, phép lấy lớn nhất thường rõ ràng.

**Thứ tự quan trọng:** xác định bài toán và miền đầu vào → chọn tham số kích thước → nêu mô hình thao tác → đếm thao tác → suy ra hàm chi phí → phát biểu giới hạn tiệm cận. Nếu bỏ bước chọn mô hình, kết luận “một phép toán mất O(1)” rất dễ bị hiểu sai.

## 2. Các mô hình thường gặp

| Mô hình | Đơn vị chi phí chính | Phù hợp với | Giới hạn cần nhớ |
|---|---|---|---|
| **RAM / word-RAM** | Một thao tác cơ bản trên một từ máy, truy cập một ô nhớ có địa chỉ | Phân tích thông thường trên mảng, chỉ số, vòng lặp, cấu trúc dữ liệu trong RAM | Giả định truy cập ô nhớ và thao tác trên từ máy có chi phí hằng số; không mô tả chi tiết cache, GC, hệ điều hành |
| **Mô hình so sánh** | Số lần so sánh hai khóa | Sắp xếp, tìm kiếm, cây tìm kiếm dựa trên so sánh | Không tính miễn phí việc xử lý khóa lớn; cận dưới cho thuật toán chỉ dùng so sánh không tự động áp dụng cho counting/radix sort |
| **Mô hình độ phức tạp bit** | Phép toán trên bit hoặc từ có kích thước bị chặn | Số nguyên rất lớn, mã hóa, mật mã, thuật toán số học | Thao tác trên số `B` bit không thể mặc định là O(1) |
| **Mô hình I/O / bộ nhớ ngoài** | Số lần chuyển khối giữa đĩa và bộ nhớ trong, thường mỗi khối có `B` phần tử/byte tùy định nghĩa | Sắp xếp tệp lớn, cơ sở dữ liệu, xử lý dữ liệu không vừa RAM | Hai thuật toán có cùng số phép CPU vẫn có thể khác rất nhiều lần đọc/ghi khối |
| **Mô hình chi phí thực nghiệm** | Thời gian chạy, bộ nhớ đỉnh, số lần cấp phát, cache miss... đo trong môi trường cụ thể | Tối ưu triển khai, kiểm tra giới hạn thực thi | Kết quả phụ thuộc máy, JVM, JIT, dữ liệu, bộ đo và số lần chạy |

### Phân biệt RAM và word-RAM

Trong mô hình RAM đơn giản, các phép cộng, so sánh và đọc/ghi ô nhớ thường có chi phí đơn vị. **Word-RAM** diễn đạt rõ hơn rằng những phép đó thao tác trên một **từ máy** có độ rộng `w` bit. Thuật toán thường cần `w` đủ lớn để lưu chỉ số của cấu trúc có `n` phần tử, tức `w ≥ ⌈log₂ n⌉` trong mô hình thích hợp.

Không thể dùng giả định “phép cộng O(1)” cho một `BigInteger` dài hàng triệu bit rồi kết luận cả thuật toán xử lý số lớn là O(n) theo số lượng toán hạng. Phải tính đến **độ dài bit của toán hạng**. Ví dụ cộng hai số nguyên có tối đa `B` bit được thực hiện trong O(B) thời gian theo mô hình bit thông dụng; nhân số lớn có chi phí tùy thuật toán nhân được sử dụng.

Tương tự, truy cập một ô mảng là O(1) trong RAM nhưng có thể chậm hoặc nhanh khác nhau trên phần cứng do cache và vị trí dữ liệu. Mô hình chủ động lược bỏ các yếu tố đó để thấy tốc độ tăng khi `n` tăng.

## 3. “Phép toán cơ bản” gồm những gì?

**Phép toán cơ bản (primitive operation)** là thao tác nhỏ nhất mà người phân tích chọn để đếm trong mô hình. Với thuật toán chạy trên số nguyên có kích thước máy, các thao tác sau thường được xem có chi phí hằng số:

- Gán giá trị cho một biến, tăng hoặc giảm một biến đếm.
- Cộng, trừ, nhân, chia hoặc lấy dư hai giá trị primitive có độ rộng cố định (không có nghĩa các phép này chạy nhanh như nhau).
- So sánh hai giá trị primitive: `<`, `<=`, `==`, `>`...
- Đọc hoặc ghi một phần tử mảng theo chỉ số hợp lệ.
- Kiểm tra điều kiện rẽ nhánh, trả về kết quả, truyền một số lượng đối số cố định.

**Không phải mọi biểu thức nhìn giống “một dòng” đều là một phép O(1).**

Ví dụ trong Java:

| Biểu thức / thao tác | Chi phí điển hình theo RAM khi chiều dài biến đổi | Ghi chú |
|---|---|---|
| `int x = a[i];` | O(1) | Giả sử chỉ số hợp lệ và mảng đã tồn tại |
| `long y = p + q;` | O(1) | Hai giá trị `long` có độ rộng cố định |
| `arr.length` hoặc `list.size()` với `ArrayList` | O(1) | Chỉ đọc kích thước được lưu |
| `new int[n]` | O(n) thời gian, O(n) bộ nhớ | Java khởi tạo các phần tử mảng về giá trị mặc định |
| `Arrays.copyOf(arr, n)` | O(n) thời gian và bộ nhớ cho mảng kết quả | Sao chép/khởi tạo `n` phần tử |
| `list.get(i)` với `ArrayList` | O(1) | Truy cập vị trí |
| `list.add(0, x)` với `ArrayList` | O(n) | Phải dịch chuyển các phần tử đang có |
| `list.add(x)` ở cuối `ArrayList` | O(1) **khấu hao** | Một lần nới dung lượng có thể tốn O(n) |
| `s.equals(t)` với hai `String` dài tối đa `L` | O(L) trường hợp xấu | Có thể dừng sớm nếu độ dài hoặc ký tự khác |
| `StringBuilder.append(s)` | O(|s|) cho việc thêm nội dung, ngoài các lần nới buffer | Nhiều lần nối có thể có chi phí khấu hao |
| `map.get(key)` với `HashMap` | Thường xét kỳ vọng gần O(1) dưới giả định băm phù hợp | Không có bảo đảm O(1) tuyệt đối cho mọi phân bố khóa và tình huống |
| `System.out.println(s)` | Phụ thuộc độ dài văn bản và môi trường I/O | Không thể in `L` ký tự mà không xử lý lượng đầu ra đó |

Các dòng trên là **mô hình để phân tích**, không phải bảng tốc độ CPU hay bảo đảm hiệu năng của mọi phiên bản JDK. Đặc biệt, tên một phương thức Java không cho biết chi phí của nó; phải nhìn thao tác bên trong và kích thước dữ liệu nó xử lý.

### Phép toán logic và đánh giá ngắn mạch

Java đánh giá `a && b` theo cách **ngắn mạch**: nếu `a` là `false` thì `b` không được tính. Tương tự, `a || b` không tính `b` nếu `a` đã là `true`.

Giả sử `a` tốn 1 đơn vị, `b` tốn `n` đơn vị. Khi viết `a && b`, một lần kiểm tra điều kiện có thể tốn từ O(1) đến O(n), tùy dữ liệu. Vì vậy, không được tính mọi câu lệnh `if` là “một thao tác hằng số” khi chính biểu thức điều kiện gọi hàm có chi phí theo `n`.

## 4. Đếm chi phí của một vòng lặp tuyến tính

Xét mã minh họa Java sau; `a` là mảng `n` phần tử đã có sẵn:

~~~java
long sum = 0;
for (int i = 0; i < a.length; i++) {
    sum += a[i];
}
~~~

Nếu `n = a.length`:

- Khởi tạo `sum = 0` thực hiện một lần.
- Khởi tạo `i = 0` thực hiện một lần.
- Kiểm tra `i < n` thực hiện **`n + 1` lần**: có `n` lần đúng và một lần sai để kết thúc.
- Đọc `a[i]`, cộng và gán cho `sum` thực hiện **`n` lần** mỗi loại.
- Cập nhật `i++` thực hiện **`n` lần**.

Khi các thao tác tương ứng có chi phí hằng số `c_1, c_2, ...`, một mô hình chi phí có dạng:

`T(n) = c_1 + c_2 + c_3(n+1) + c_4 n + c_5 n = a n + b`,

với `a, b` là các hằng số không phụ thuộc `n`. Khi `a > 0` và `n` tăng, ta kết luận **`T(n) = Θ(n)`**.

Điểm dễ sai: lần kiểm tra cuối cùng tuy không thực hiện thân vòng lặp vẫn phải được đếm nếu ta phân tích số phép kiểm tra. Nhưng khi chỉ cần đánh giá bậc tăng, việc thêm 1 phép kiểm tra không làm thay đổi `Θ(n)`.

**Đối với Java:** `sum` ở ví dụ là `long`, nhưng nếu mọi `a[i]` rất lớn và `n` đủ lớn để tổng vượt miền `long`, phép cộng vẫn có thể tràn. Khi dùng mô hình RAM để khẳng định thuật toán tính đúng, cần tách hai giả thiết: **chi phí** của phép cộng và **miền giá trị** đảm bảo kết quả phép cộng có nghĩa mong muốn.

## 5. Đếm phép toán trong vòng lặp lồng nhau

Hai vòng lặp không mặc nhiên có độ phức tạp O(n²); cần đếm **số lần thân trong cùng được thực hiện**.

### 5.1. Duyệt tất cả cặp chỉ số

~~~java
long pairs = 0;
for (int i = 0; i < n; i++) {
    for (int j = i + 1; j < n; j++) {
        pairs++;
    }
}
~~~

Với mỗi `i`, thân vòng trong chạy `n − i − 1` lần. Tổng số lần tăng biến `pairs` là:

`(n−1) + (n−2) + ... + 1 + 0 = n(n−1)/2`.

Vì vậy `T(n) = Θ(n²)` khi `n` lớn. Với `n = 5`, thân chạy đúng `4+3+2+1+0 = 10` lần. Nếu phân tích cả điều kiện `j < n`, điều kiện trong được kiểm tra `n(n+1)/2` lần vì mỗi lượt của vòng ngoài còn một lần kiểm tra sai. Điều này làm thay đổi **hằng số và số hạng bậc thấp**, không làm thay đổi `Θ(n²)`.

### 5.2. Hai con trỏ cùng tiến về phía trước

~~~java
int left = 0;
int right = 0;
while (left < n && right < n) {
    if (shouldMoveLeft(left, right)) {
        left++;
    } else {
        right++;
    }
}
~~~

Đoạn này chỉ là **mã minh họa**, cần định nghĩa `shouldMoveLeft` trước khi chạy độc lập. Giả sử mỗi lần gọi hàm đó tốn O(1), mỗi vòng lặp tăng **ít nhất một** con trỏ và hai con trỏ không giảm. Mỗi con trỏ tăng tối đa `n` lần, nên số vòng lặp không vượt `2n` và tổng chi phí là O(n). Đây là minh họa cho việc **mô hình đếm tiến trình của con trỏ** có giá trị hơn việc đếm số biến hoặc số vòng một cách hình thức.

Nếu `shouldMoveLeft` thực tế phải quét cả dãy O(n), toàn bộ thời gian có thể lên đến O(n²). Ta phải cộng chi phí lời gọi hàm vào thân vòng.

### 5.3. Bước nhảy nhân đôi

~~~java
for (long step = 1; step < n; step *= 2) {
    // Thao tác O(1)
}
~~~

Với số nguyên `n ≥ 1`, số lần thực hiện thân là `⌈log₂ n⌉` (bằng 0 khi `n=1`). Dùng `long` cho `step` giúp tránh tràn sớm khi `n` là một giá trị `int` dương lớn. Kết quả là `O(log n)`; nếu thân làm số công việc hằng số dương mỗi lần thì `Θ(log n)` trong trường hợp `n` tăng.

## 6. Câu lệnh điều kiện và lời gọi hàm

Xét cấu trúc:

~~~java
if (condition) {
    doA();
} else {
    doB();
}
~~~

Ký hiệu `T_cond(n)`, `T_A(n)` và `T_B(n)` lần lượt là chi phí của điều kiện và nhánh. Với một đầu vào cụ thể, chỉ nhánh được chọn chạy:

`T(x) = T_cond(x) + [condition(x) ? T_A(x) : T_B(x)] + O(1)`.

Nếu muốn **cận trên xấu nhất** theo kích thước, ta có thể dùng:

`T_worst(n) ≤ T_cond,worst(n) + max(T_A,worst(n), T_B,worst(n)) + O(1)`.

Đây là **cận trên an toàn**; không nhất thiết là biểu thức chính xác vì không phải mọi đầu vào khiến cả điều kiện và nhánh đắt nhất cùng xảy ra.

Đối với các lời gọi hàm, cộng chi phí thực sự của hàm được gọi: một chương trình có `n` lần gọi hàm `f` mà mỗi lần mất `Θ(n)` có thể tốn `Θ(n²)`, dù thân vòng ngoài chỉ có một lời gọi. Ngược lại, nếu hàm `f` có chi phí thay đổi theo tham số `i`, phải tính tổng `Σ_i T_f(i)` thay vì nhân vô điều kiện `n · T_f(n)`.

**Đệ quy** thường được mô tả bằng hệ thức truy hồi. Ví dụ, với một thuật toán chia đôi thành hai bài toán bằng nhau và công đoạn ghép tuyến tính:

`T(n) = 2 T(n/2) + Θ(n)`,

thường dẫn đến `T(n)=Θ(n log n)` dưới các điều kiện kích thước/base case thích hợp. Phần quan trọng ở bài học này là **mỗi hạng tử của hệ thức phải đại diện đúng cho một phần chi phí**, không xuất phát từ việc đếm số dòng mã.

## 7. Số phép toán chính xác, ký hiệu O, Ω và Θ

Ba ký hiệu hay gặp mô tả **tốc độ tăng của hàm chi phí**, không trực tiếp biểu diễn thời gian theo giây:

- `f(n)=O(g(n))`: `f` được chặn **trên** bởi một hằng số nhân với `g` kể từ kích thước đủ lớn.
- `f(n)=Ω(g(n))`: `f` được chặn **dưới** bởi một hằng số dương nhân với `g` kể từ kích thước đủ lớn.
- `f(n)=Θ(g(n))`: tồn tại cả hai cận trên và dưới nói trên, tức cùng bậc tăng.

Ví dụ đếm cặp có đúng `n(n−1)/2` lần thực hiện thân, nên đồng thời thuộc `O(n²)`, `Ω(n²)` và `Θ(n²)`. Viết chỉ “`O(n²)`” là đúng khi nói cận trên nhưng chưa diễn đạt hết thông tin có được.

Khi chọn **phép toán cơ bản** để đếm, người ta thường đếm thao tác lặp lại nhiều nhất trong phần chi phối, như phép so sánh của tìm kiếm. Nếu mọi thao tác khác tốn không quá một số cố định lần thao tác cơ bản trên mỗi lượt, chi phí đếm được thường đủ để xác định bậc tăng. Tuy nhiên, đây là một **lập luận phải kiểm tra**, không phải quy tắc đúng với mọi đoạn mã, đặc biệt khi có phép toán trên dữ liệu dài, cấp phát khối lớn hoặc I/O.

## 8. Tốt nhất, xấu nhất, trung bình và khấu hao

Với cùng kích thước đầu vào `n`, thuật toán có thể thực hiện số thao tác khác nhau tùy dữ liệu.

**Ví dụ tìm kiếm tuyến tính** một khóa `target` trong mảng `n` phần tử:

- **Tốt nhất (best case):** khóa ở ngay vị trí đầu, cần 1 phép so sánh khóa nếu `n > 0` → `Θ(1)`.
- **Xấu nhất (worst case):** không thấy khóa hoặc khóa ở vị trí cuối, cần `n` phép so sánh → `Θ(n)`.
- **Trung bình (average case):** cần xác định phân bố đầu vào. Nếu bảo đảm khóa xuất hiện đúng một lần và vị trí của nó phân bố đều trong `1..n`, số so sánh kỳ vọng là `(1+2+...+n)/n = (n+1)/2` → `Θ(n)`. Nếu có xác suất không tìm thấy hoặc vị trí không đều, kết quả kỳ vọng thay đổi.
- **Khấu hao (amortized):** đánh giá chi phí trung bình **trên một chuỗi thao tác**, kể cả những thao tác hiếm nhưng đắt; không đồng nghĩa với trung bình xác suất. Ví dụ thêm cuối `ArrayList` thường rẻ, đôi khi phải cấp phát mảng lớn hơn và sao chép; chi phí thêm cuối được phân tích khấu hao O(1) qua nhiều lần thêm, còn một lần cụ thể có thể O(n).

**Không đánh tráo mô hình:** “trung bình” là kỳ vọng theo một giả thiết phân bố đã nêu; “khấu hao” là bảo đảm tổng chi phí trên chuỗi thao tác mà không cần giả định phân bố ngẫu nhiên.

## 9. Ví dụ Java 17+ hoàn chỉnh: đếm thao tác có chủ đích

Chương trình sau **đo hai loại thao tác được định nghĩa rõ** trong tìm kiếm tuyến tính: số lần đọc phần tử mảng và số lần so sánh phần tử với khóa. Nó cũng đếm số cặp chỉ số `(i,j)` với `i < j`.

Lưu dưới tên `CostModelDemo.java`:

~~~java
public final class CostModelDemo {
    record SearchResult(int index, long comparisons, long reads) {}

    static SearchResult linearSearch(int[] data, int target) {
        long comparisons = 0;
        long reads = 0;

        for (int i = 0; i < data.length; i++) {
            int value = data[i];
            reads++;

            comparisons++;
            if (value == target) {
                return new SearchResult(i, comparisons, reads);
            }
        }
        return new SearchResult(-1, comparisons, reads);
    }

    static long countPairs(int n) {
        long pairs = 0;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                pairs++;
            }
        }
        return pairs;
    }

    public static void main(String[] args) {
        int[] data = {7, 2, 9, 2, 5};

        SearchResult found = linearSearch(data, 9);
        SearchResult absent = linearSearch(data, 4);

        System.out.printf(
                "Found: index=%d, comparisons=%d, reads=%d%n",
                found.index(), found.comparisons(), found.reads()
        );
        System.out.printf(
                "Missing: index=%d, comparisons=%d, reads=%d%n",
                absent.index(), absent.comparisons(), absent.reads()
        );
        System.out.println("Pairs: " + countPairs(data.length));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CostModelDemo.java
java CostModelDemo
~~~

Kết quả chuẩn chính xác:

~~~text
Found: index=2, comparisons=3, reads=3
Missing: index=-1, comparisons=5, reads=5
Pairs: 10
~~~

**Giải thích kết quả**

- Mảng `{7,2,9,2,5}` có 5 phần tử. Khóa `9` được gặp lần thứ ba ở chỉ số 2 (đánh số từ 0), nên đọc và so sánh 3 phần tử.
- Khóa `4` không xuất hiện nên phải đọc và so sánh cả 5 phần tử.
- Có `5·4/2 = 10` cặp chỉ số khác nhau thỏa `i < j`.
- Chương trình **không đếm** kiểm tra vòng lặp `i < data.length`, tăng chỉ số, tạo `SearchResult`, gán biến hoặc các phép tăng bộ đếm. Đây là lựa chọn định nghĩa thao tác cần quan sát, **không phải số lệnh CPU**. Việc chèn bộ đếm vào mã còn làm chương trình chạy thêm thao tác.
- Tìm kiếm tuyến tính có **`O(n)` thời gian xấu nhất** và `O(1)` bộ nhớ phụ; đếm cặp bằng hai vòng lặp có **`Θ(n²)` thời gian** và `O(1)` bộ nhớ phụ. Biến đếm `long` an toàn cho `countPairs(200_000)`: kết quả là `19_999_900_000`, vượt giới hạn `int`.

Nếu muốn đếm **tất cả lần kiểm tra điều kiện vòng lặp**, phải thêm bộ đếm riêng và định nghĩa rõ việc đếm các lần kiểm tra sai cuối cùng. Với tìm kiếm tuyến tính bị trượt hoàn toàn trên `n` phần tử, phép kiểm tra `i < n` được đánh giá `n+1` lần, còn phép so sánh `value == target` chỉ được đánh giá `n` lần.

## 10. Quy mô dữ liệu và phép toán trên số lớn

Trong các bài toán thường gặp, độ phức tạp `O(n)` ngầm coi cộng, so sánh và truy cập chỉ số primitive có chi phí không đổi. Khi dữ liệu là số có chiều dài `B` bit, **kích thước đầu vào theo số phần tử** có thể chưa đủ:

- Đọc một số có `B` bit hoặc `D` chữ số thập phân cần xử lý lượng dữ liệu tương ứng; không thể xem việc nhập một số rất dài là O(1).
- So sánh hai số nguyên dài tối đa `B` bit có chi phí O(B) trong trường hợp xấu theo một mô hình bit tự nhiên; có thể kết thúc sớm nếu khác dấu, khác độ dài hoặc khác ở phần đầu đáng kể.
- Cộng hai số `B` bit có chi phí tuyến tính O(B) theo cách biểu diễn nhị phân thông thường; phép nhân có các thuật toán với chi phí khác nhau và không thể mặc định O(1).
- Hai thuật toán “đều thực hiện `n` phép cộng” chưa có cùng độ phức tạp bit nếu độ dài toán hạng trung gian của chúng tăng khác nhau.

**Trong Java**, `int` và `long` có độ rộng cố định nên thao tác số học primitive được phân tích O(1) ở mức word-RAM. `BigInteger` lưu độ chính xác tùy ý, nên phải xem cả độ dài toán hạng; chi phí của từng phương thức còn phụ thuộc thuật toán triển khai. Đừng nhầm “không tràn số” với “không tăng chi phí”.

Tương tự với văn bản: truy cập `s.charAt(i)` trên `String` hợp lệ thường được xem O(1) theo đơn vị mã UTF-16; nhưng so sánh hai chuỗi dài `L` ký tự bằng `equals` có thể cần xem nhiều vị trí. Số đơn vị mã UTF-16 khác số code point hoặc số grapheme; chọn đúng tham số kích thước khi đề bài nói “ký tự”.

## 11. Chi phí thời gian và chi phí bộ nhớ là hai hàm khác nhau

Ngoài `T(n)`, ta thường phân tích `S(n)` là bộ nhớ sử dụng theo `n`. Cần nói rõ đang đếm **bộ nhớ tổng** hay **bộ nhớ phụ**, có tính vùng lưu đầu vào/đầu ra không.

Ví dụ:

| Thuật toán/đoạn mã | Thời gian theo RAM | Bộ nhớ phụ |
|---|---|---|
| Tìm phần tử lớn nhất của mảng có sẵn | Θ(n) | Θ(1) |
| Sao chép `n` phần tử sang mảng mới | Θ(n) | Θ(n) |
| Đếm mọi cặp chỉ số mà không lưu kết quả | Θ(n²) | Θ(1) |
| Tạo danh sách chứa mọi cặp chỉ số | Ít nhất Θ(n²) | Θ(n²) để giữ các cặp |
| Tìm kiếm nhị phân lặp trên mảng đã sắp xếp | O(log n) | Θ(1) |

**Một thao tác cấp phát cũng có chi phí.** Trong Java, `new int[n]` không nên được tính như một phép gán đơn vị O(1): vùng chứa `n` số nguyên phải được cấp phát và khởi tạo. Đệ quy còn dùng ngăn xếp gọi hàm; ngay cả khi mỗi mức chỉ giữ vài biến, độ sâu `n` có thể cần O(n) ngăn xếp và gặp `StackOverflowError`.

Đối với tệp lớn, số byte đọc/ghi hoặc số lần chuyển khối có thể quan trọng hơn số phép cộng. Thuật toán chỉ duyệt dữ liệu một lần thường có ưu thế I/O so với thuật toán quét lại nhiều lần, nhưng cần xét kích thước bộ đệm và khuôn dạng dữ liệu thực tế.

## 12. Từ phép đếm lý thuyết đến đo đạc Java

Đếm phép toán giải thích **khả năng mở rộng**, còn benchmark cho thấy **hiệu năng trên môi trường cụ thể**. Để hai phép đo có ý nghĩa:

1. Xác định đúng đại lượng: số so sánh khóa, số lần truy cập phần tử, lượng dữ liệu sao chép, byte I/O, thời gian thực hay bộ nhớ đỉnh. Không gọi tất cả chúng chung là “số phép toán”.
2. Dùng đầu vào đại diện cho cả trường hợp tốt, xấu và quy mô lớn; công bố `n`, cách sinh dữ liệu và ràng buộc miền giá trị.
3. Với JVM, xét việc khởi động, warmup/JIT, GC, cấp phát và sai số của đồng hồ. `System.nanoTime()` cho thời gian tương đối; một lần đo đơn lẻ thường không đủ để kết luận.
4. Tránh tối ưu hóa vô hiệu hóa công việc cần đo; không để thời gian tạo dữ liệu hoặc in kết quả lấn át thao tác đang so sánh nếu mục tiêu là chi phí thuật toán thuần.
5. Khi cần microbenchmark Java, dùng một công cụ được thiết kế cho việc đó như JMH và công bố cách chạy. Số nanosecond đo được không tự động chứng minh một biểu thức `Θ(...)`.

Một thuật toán `Θ(n log n)` có thể chạy nhanh hơn thuật toán `Θ(n)` trên dữ liệu nhỏ do hằng số và chi phí môi trường. Với `n` rất lớn, khác biệt về bậc tăng trở nên quan trọng hơn. Ký hiệu tiệm cận không thay thế kiểm thử hiệu năng khi có hạn mức thời gian và bộ nhớ cụ thể.

## 13. Lỗi thường gặp và cách tự kiểm tra

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| “Một dòng lệnh = một phép O(1)” | Một dòng có thể sao chép, so sánh chuỗi hoặc cấp phát O(n) | Phân rã các thao tác và nhìn vào kích thước dữ liệu |
| “Hai vòng lặp = O(n²)” | Con trỏ có thể chỉ tiến tổng cộng O(n) lần | Đếm đúng số lần thực hiện thân và điều kiện |
| “Một phép cộng luôn O(1)” | Số nguyên tùy ý có độ dài tăng | Nêu rõ kiểu primitive/word-RAM hay mô hình bit |
| “Điều kiện `if` luôn O(1)” | Điều kiện có thể gọi hàm O(n) | Tính cả chi phí đánh giá điều kiện và ngắn mạch |
| “Đếm chính xác phép so sánh tức là thời gian CPU” | Bộ đếm bỏ qua nhiều lệnh và hệ thống bộ nhớ | Ghi rõ loại phép toán đếm và mô hình |
| “Worst case, average case và amortized giống nhau” | Ba cách gom chi phí dựa trên định nghĩa khác nhau | Nêu phân bố xác suất hoặc chuỗi thao tác tương ứng |
| “`O(n)` đồng nghĩa luôn tốt” | Hệ số, I/O, cấp phát và giới hạn bộ nhớ có thể lớn | Phân tích cả hằng số quan trọng và kiểm thử thực tế |
| “`O(n)` cho bài có `n` số nguyên rất dài” | Chi phí thao tác tùy độ dài bit của mỗi số | Thêm tham số `B` hoặc tính theo tổng độ dài bit |

**Checklist để tự phân tích một đoạn mã:**

1. Kích thước `n` đo bằng phần tử, byte, bit hay một bộ tham số (`V,E,Q,...`)?
2. Đầu vào nào được xem hợp lệ, và các giá trị trung gian có vừa kiểu dữ liệu không?
3. Mô hình RAM, so sánh, bit hay I/O đang dùng; thao tác cơ bản cụ thể là gì?
4. Mỗi thao tác chạy bao nhiêu lần? Vòng lặp có lần kiểm tra sai cuối cùng không; lời gọi hàm bên trong có tốn theo `n` không?
5. Cần số đếm chính xác, cận trên O, cận dưới Ω hay cận chặt Θ? Là tốt nhất, xấu nhất, trung bình hay khấu hao?
6. Chi phí bộ nhớ phụ, cấp phát, ngăn xếp, I/O có được tính tách bạch chưa?
7. Nếu đo trên JVM, dữ liệu và cách benchmark có đại diện cho kết luận cần rút ra không?

**Kết luận:** Đếm phép toán chỉ có ý nghĩa khi biết **đang đếm thao tác nào, trên loại dữ liệu nào và theo giả định chi phí nào**. Một phân tích tốt đưa ra được hàm chi phí hoặc giới hạn tiệm cận có lập luận, đồng thời nhận rõ các chi phí thực thi mà mô hình đã trừu tượng hóa.