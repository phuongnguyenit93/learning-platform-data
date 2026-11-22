# Sắp xếp nhiều khóa và xử lý phần tử bằng nhau

Trong nhiều bài toán thực tế, mỗi bản ghi có **nhiều thuộc tính**. Ví dụ: xếp danh sách học viên theo **điểm giảm dần**, nếu điểm bằng nhau thì theo **lớp tăng dần**, tiếp đó theo **tên tăng dần**. Thuật toán phải biết **khóa nào ưu tiên trước**, mỗi khóa tăng hay giảm, và cách xử lý các phần tử vẫn bằng nhau sau khi so sánh hết mọi khóa.

Đây là bài toán **sắp xếp so sánh** (comparison sorting). Kỹ năng trọng tâm là xây dựng thứ tự từ nhiều khóa, hiểu **tính ổn định (stability)**, phân biệt **khóa bằng nhau** với **bản ghi giống hệt nhau**, và dùng Comparator đúng trong Java 17+.

## 1. Mô hình bài toán và thứ tự ưu tiên của khóa

Một bản ghi có thể viết dưới dạng **r = (k₁, k₂, ..., kₘ, dữ liệu khác)**. Ta chọn thứ tự ưu tiên:

1. **Khóa chính (primary key)**: tiêu chí quan trọng nhất.
2. **Khóa phụ thứ nhất (secondary key)**: chỉ dùng nếu khóa chính bằng nhau.
3. **Khóa phụ tiếp theo**: chỉ dùng nếu toàn bộ khóa ưu tiên cao hơn đều bằng nhau.
4. Nếu mọi khóa được chọn đều bằng nhau, hai bản ghi được coi là **ngang hạng theo tiêu chí sắp xếp**. Khi đó cần quy định có giữ thứ tự gốc hay bổ sung tiêu chí phá hòa.

Ví dụ có tám bản ghi:

| Mã | Lớp | Điểm | Tên |
| --- | --- | ---: | --- |
| S01 | B | 90 | Lan |
| S02 | A | 90 | Minh |
| S05 | A | 90 | An |
| S04 | B | 75 | Ha |
| S03 | A | 90 | An |
| S06 | A | 75 | Binh |
| S07 | B | 90 | An |
| S08 | A | 75 | An |

Yêu cầu:

- **Điểm giảm dần**: 90 đứng trước 75.
- Khi điểm bằng nhau, **lớp tăng dần**: A đứng trước B.
- Khi cả điểm và lớp bằng nhau, **tên tăng dần**: An trước Minh, An trước Lan trong cùng lớp nếu phù hợp.
- Nếu cả ba khóa cùng bằng nhau, **giữ thứ tự gốc**.

Kết quả theo thứ tự **mã bản ghi**:

~~~text
[S05, S03, S02, S07, S01, S08, S06, S04]
~~~

Ở nhóm (điểm 90, lớp A, tên An), **S05** xuất hiện trước **S03** trong dữ liệu gốc nên vẫn đứng trước. Điều này phụ thuộc vào việc thuật toán được sử dụng **ổn định**.

### Thứ tự nhiều khóa là thứ tự từ điển (lexicographic)

So sánh hai bản ghi x và y theo thứ tự ưu tiên: so khóa chính, nếu khác thì kết luận ngay; nếu bằng mới xét khóa phụ. Đây là cùng nguyên tắc so sánh cặp hoặc bộ nhiều thành phần theo thứ tự từ điển.

Ví dụ **x = (90, A, Minh)** và **y = (90, B, An)**: điểm bằng nhau, lớp A đứng trước B, nên x đứng trước y **bất kể** tên Minh hay An. Không được so tên trước lớp khi lớp được ưu tiên cao hơn.

## 2. Bộ so sánh (Comparator) là hợp đồng quan trọng nhất

Một hàm so sánh **compare(x, y)** có quy ước:

- Trả số **âm** nếu x đứng trước y.
- Trả **0** nếu x và y ngang hạng theo các khóa đã chọn.
- Trả số **dương** nếu x đứng sau y.

Chỉ **dấu** của kết quả có ý nghĩa; không được giả định luôn trả đúng −1, 0 hoặc 1.

Giả mã comparator cho ba khóa:

~~~text
compare(x, y):
    c = compareDescending(x.score, y.score)
    if c != 0: return c

    c = compareAscending(x.team, y.team)
    if c != 0: return c

    c = compareAscending(x.name, y.name)
    return c
~~~

Tính chất của một comparator hợp lệ:

- **Phản đối xứng theo dấu:** sign(compare(x,y)) = −sign(compare(y,x)).
- **Bắc cầu:** nếu x < y và y < z thì x < z.
- **Nhất quán khi so bằng:** nếu compare(x,y) = 0 thì mọi z phải được so với x và y theo dấu tương thích; không thể đôi lúc xem x và y ngang nhau nhưng lại xếp chúng khác hướng đối với cùng z.
- **Ổn định trong khi sắp:** kết quả không được đổi bất thường do trạng thái bên ngoài hoặc việc sửa khóa.

Nếu các tính chất trên bị vi phạm, thuật toán sắp xếp có thể cho kết quả không hợp lệ; một số cài đặt Java có thể phát hiện comparator vi phạm hợp đồng và ném **IllegalArgumentException**.

### Tăng dần và giảm dần ở từng khóa

- **Tăng dần (ascending):** số nhỏ hơn trước, chuỗi nhỏ hơn theo bộ so sánh trước.
- **Giảm dần (descending):** số lớn hơn trước, chuỗi lớn hơn theo bộ so sánh trước.
- Mỗi khóa có **chiều riêng**, ví dụ (điểm DESC, lớp ASC, tên ASC).

Dễ sai khi đảo chiều **toàn bộ** comparator sau khi đã nối các khóa. Chẳng hạn:

~~~java
Comparator<Student> wrong = Comparator
        .comparingInt(Student::score)
        .thenComparing(Student::team)
        .thenComparing(Student::name)
        .reversed();
~~~

Đoạn trên đảo **điểm, lớp và tên** cùng lúc. Muốn chỉ đảo điểm, phải đảo comparator của điểm **trước khi** nối các khóa phụ.

## 3. Tính ổn định và phần tử bằng nhau

Một thuật toán sắp xếp gọi là **ổn định (stable)** nếu với mọi cặp bản ghi x, y **bằng nhau theo comparator**, thứ tự tương đối trước/sau của chúng **không thay đổi** sau khi sắp.

Ví dụ:

~~~text
Trước:  (90,S05) (75,S04) (90,S03)
Sắp ổn định theo điểm giảm dần:
        (90,S05) (90,S03) (75,S04)
~~~

Hai bản ghi điểm 90 có vị trí gốc S05 rồi S03 nên kết quả vẫn là S05 rồi S03. Nếu xếp bằng thuật toán **không ổn định** mà không thêm khóa phụ, thứ tự của chúng có thể đổi.

Điều cần phân biệt:

- **Bằng nhau về khóa:** Comparator.compare(x, y) == 0. Hai bản ghi có thể vẫn khác mã, ngày tạo, địa chỉ hoặc dữ liệu khác.
- **Bằng nhau về toàn bộ bản ghi:** tùy định nghĩa equals và cấu trúc lưu trữ.
- **Tính ổn định:** giữ thứ tự gốc cho các bản ghi ngang hạng theo comparator, **không tự loại bỏ bản ghi trùng**.
- **Quy tắc phá hòa (tie-breaker):** thêm khóa như mã, thời gian tạo hoặc chỉ số gốc để quyết định thứ tự khi các khóa chính bằng nhau.

Nếu muốn **thứ tự hoàn toàn xác định bất kể đầu vào ban đầu**, hãy thêm một khóa phụ phù hợp, chẳng hạn **mã định danh duy nhất tăng dần**. Nếu muốn **bảo toàn thứ tự của dữ liệu nguồn**, dùng thuật toán ổn định và **không thêm** một tiêu chí phá hòa mâu thuẫn với thứ tự nguồn.

### Tại sao thêm mã ID làm thay đổi kết quả?

Với hai bản ghi S05 và S03 cùng (điểm 90, lớp A, tên An):

- Chỉ so ba khóa và sắp ổn định → **S05 trước S03** theo dữ liệu gốc.
- So ba khóa rồi thêm **ID tăng dần** → **S03 trước S05**, bất kể thứ tự nhập.

Cả hai đều có thể đúng; phải dựa vào đặc tả đề bài để chọn.

## 4. Java 17+: nối Comparator cho nhiều khóa

Trong Java, **Comparator.comparing**, **comparingInt**, **thenComparing** và **reversed** cho phép xây bộ so sánh dễ đọc, ít lỗi.

~~~java
Comparator<Student> order = Comparator
        .comparingInt(Student::score).reversed()
        .thenComparing(Student::team)
        .thenComparing(Student::name);
~~~

Ý nghĩa chính xác:

1. **comparingInt(Student::score)** so điểm tăng dần bằng số nguyên.
2. **reversed()** chỉ đảo comparator điểm tại thời điểm này → điểm giảm dần.
3. **thenComparing(Student::team)** thêm lớp tăng dần khi điểm bằng nhau.
4. **thenComparing(Student::name)** thêm tên tăng dần khi điểm và lớp bằng nhau.

Nếu cần **điểm giảm dần, lớp tăng dần, tên giảm dần**, có thể viết:

~~~java
Comparator<Student> order = Comparator
        .comparingInt(Student::score).reversed()
        .thenComparing(Student::team)
        .thenComparing(Student::name, Comparator.reverseOrder());
~~~

Ở phiên bản này, chỉ comparator của **tên** được đảo. Đừng đặt **reversed()** ở cuối chuỗi khi chỉ muốn đổi chiều một khóa.

### Tránh tràn số khi so sánh số nguyên

Mã sau có nguy cơ tràn số:

~~~java
(a, b) -> b.score() - a.score()
~~~

Nếu score là các giá trị int cực lớn trái dấu, phép trừ có thể tràn và đảo kết quả so sánh. Dùng **Integer.compare(b.score(), a.score())**, **Comparator.comparingInt(...).reversed()**, hoặc kiểu so sánh thích hợp với miền dữ liệu.

Nếu khóa là **long**, dùng **Long.compare** hoặc **comparingLong** thay vì ép về int. Với **double**, dùng **Double.compare/comparingDouble** và hiểu quy tắc của Java đối với NaN, các giá trị vô cực và +0.0/−0.0; không tự viết phép so sánh với kết quả thiếu nhất quán.

## 5. Chương trình Java 17+ chạy độc lập

Chương trình tạo các bản ghi theo đúng thứ tự bảng ở mục 1 và sắp theo ba khóa **điểm giảm → lớp tăng → tên tăng**. Sau đó minh họa **sắp nhiều lượt từ khóa ít ưu tiên đến khóa ưu tiên nhất** và so sánh với trường hợp thêm **ID** làm khóa phá hòa.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class MultiKeySortingDemo {

    record Student(String id, String team, int score, String name) {}

    static List<String> ids(List<Student> students) {
        return students.stream().map(Student::id).toList();
    }

    public static void main(String[] args) {
        List<Student> source = List.of(
                new Student("S01", "B", 90, "Lan"),
                new Student("S02", "A", 90, "Minh"),
                new Student("S05", "A", 90, "An"),
                new Student("S04", "B", 75, "Ha"),
                new Student("S03", "A", 90, "An"),
                new Student("S06", "A", 75, "Binh"),
                new Student("S07", "B", 90, "An"),
                new Student("S08", "A", 75, "An")
        );

        Comparator<Student> order = Comparator
                .comparingInt(Student::score).reversed()
                .thenComparing(Student::team)
                .thenComparing(Student::name);

        List<Student> chained = new ArrayList<>(source);
        chained.sort(order);

        // Nhieu luot sort on dinh: khoa it uu tien -> uu tien nhat.
        List<Student> multiPass = new ArrayList<>(source);
        multiPass.sort(Comparator.comparing(Student::name));
        multiPass.sort(Comparator.comparing(Student::team));
        multiPass.sort(Comparator.comparingInt(Student::score).reversed());

        // ID pha hoa, cho thu tu xac dinh doc lap vi tri nhap.
        List<Student> withId = new ArrayList<>(source);
        withId.sort(order.thenComparing(Student::id));

        System.out.println("Input: " + ids(source));
        System.out.println("Chained: " + ids(chained));
        System.out.println("Multi-pass: " + ids(multiPass));
        System.out.println("With ID: " + ids(withId));
        System.out.println("Tie S05/S03: "
                + order.compare(source.get(2), source.get(4)));
    }
}
~~~

Lưu thành **MultiKeySortingDemo.java**. Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac MultiKeySortingDemo.java
java MultiKeySortingDemo
~~~

Kết quả chuẩn:

~~~text
Input: [S01, S02, S05, S04, S03, S06, S07, S08]
Chained: [S05, S03, S02, S07, S01, S08, S06, S04]
Multi-pass: [S05, S03, S02, S07, S01, S08, S06, S04]
With ID: [S03, S05, S02, S07, S01, S08, S06, S04]
Tie S05/S03: 0
~~~

**Giải thích:**

- **Chained** dùng một comparator so lần lượt ba khóa và gọi **List.sort** một lần.
- **Multi-pass** sắp ổn định từ **tên** (khóa ít ưu tiên), đến **lớp**, cuối cùng đến **điểm** (khóa ưu tiên nhất), nên cho cùng kết quả.
- **With ID** nối thêm mã tăng dần; S03 đứng trước S05 do mã nhỏ hơn, khác với quy tắc giữ thứ tự nguồn.
- **Tie S05/S03 = 0** vì cả hai bản ghi có điểm 90, lớp A và tên An. Mã ID không nằm trong comparator **order**, nên không dùng để phân thứ tự.
- **source** là List.of không cho phép sửa cấu trúc; chương trình tạo **ArrayList bản sao** để sắp mà không thay đổi dữ liệu nguồn.

Trong Java, **List.sort(Comparator)** và **Arrays.sort(Object[])** có hợp đồng **ổn định** theo comparator. Không suy ra mọi thuật toán tự cài đều ổn định: quicksort hoặc heapsort phiên bản thông thường có thể làm đổi thứ tự bản ghi ngang hạng.

## 6. Nhiều lượt sắp ổn định: từ khóa ít ưu tiên đến khóa ưu tiên nhất

Có hai cách thiết kế phổ biến để sắp theo nhiều khóa:

**Cách A — Một lượt dùng comparator ghép:** lần lượt so khóa ưu tiên cao đến thấp trong mỗi lần gọi compare. Đây thường là cách dễ đọc và hiệu quả cho nhiều tiêu chí cố định.

**Cách B — Nhiều lượt sắp ổn định:** sắp theo khóa **ít ưu tiên nhất trước**, rồi sắp theo khóa ưu tiên cao dần cho đến khóa chính. Vì mỗi lần sắp ổn định, thứ tự vừa tạo bởi các khóa phụ được giữ nguyên trong những nhóm có khóa mới bằng nhau.

Ví dụ yêu cầu (điểm DESC, lớp ASC, tên ASC):

1. Sort ổn định theo **tên ASC**.
2. Sort ổn định theo **lớp ASC**.
3. Sort ổn định theo **điểm DESC**.

Nếu làm ngược, chẳng hạn sort điểm trước rồi tên cuối, tiêu chí tên có thể trở thành ưu tiên cao nhất, trái đề bài.

### Chứng minh ngắn cho nhiều lượt

Sau lượt sắp theo tên, mọi bản ghi đã được sắp theo tên tăng. Lượt sắp theo lớp giữ nguyên thứ tự tên **trong mỗi nhóm lớp bằng nhau** vì stable, nên danh sách đúng thứ tự (lớp ASC, tên ASC). Lượt sắp theo điểm giữ nguyên thứ tự (lớp, tên) **trong từng nhóm điểm bằng nhau**, nên kết quả đúng thứ tự (điểm DESC, lớp ASC, tên ASC).

Nếu bất kỳ lượt sắp nào **không ổn định**, thứ tự của các khóa đã xử lý có thể bị phá khi khóa hiện tại bằng nhau. Phương pháp nhiều lượt vì vậy cần bảo đảm **tất cả lượt đều stable**.

### Chi phí của hai cách

Với n phần tử và k khóa:

- Một lượt dùng comparator ghép: thuật toán sắp so sánh phổ biến mất **O(n log n)** lượt so sánh trong trường hợp xấu nhất; mỗi lần so có thể phải kiểm tra tối đa k khóa → chi phí xét khóa có thể đến **O(k n log n)** nếu mỗi phép so khóa có chi phí hằng.
- k lượt sắp ổn định: tổng cộng **k** lượt, mỗi lượt thông thường O(n log n), tức **O(k n log n)** theo mô hình chung.
- Với **k cố định** và thao tác so mỗi khóa O(1), cả hai đều thuộc **O(n log n)** theo n. Một lượt thường giảm số lần gọi thuật toán sắp, nhưng hiệu năng thực tế còn phụ thuộc phân bố khóa, chi phí Comparator và tối ưu nội bộ.

Nếu khóa là chuỗi dài, so sánh chuỗi không nhất thiết O(1); cần tính chi phí so chuỗi hoặc cache khóa đã chuẩn hóa nếu chúng được dùng rất nhiều lần.

## 7. Trùng khóa, trùng bản ghi và loại bỏ phần tử trùng

Sắp xếp và loại bản ghi trùng là **hai công việc khác nhau**.

Giả sử dữ liệu:

~~~text
(ID=A, score=80)
(ID=B, score=80)
(ID=C, score=90)
~~~

Sắp theo score tăng dần cho ra A, B, C nếu stable. Bản ghi A và B **bằng nhau theo khóa score**, nhưng là **hai bản ghi khác nhau**. Không được tự bỏ một trong hai chỉ vì comparator trả 0.

Phân biệt rõ:

| Khái niệm | Định nghĩa | Kết quả của A và B |
| --- | --- | --- |
| Bằng nhau về khóa score | score(A) = score(B) | Có |
| Bằng nhau về ID | id(A) = id(B) | Không |
| Bằng nhau theo comparator chỉ so score | compare(A,B) = 0 | Có |
| Bằng nhau về bản ghi | Theo equals hoặc quy tắc nghiệp vụ | Thường không |
| Tính ổn định | Giữ A trước B nếu A nhập trước | Có với sort ổn định |

**TreeSet/TreeMap có quy tắc đặc biệt:** chúng dùng kết quả so sánh của Comparator để quyết định các khóa có là cùng một khóa trong cấu trúc có thứ tự hay không. Nếu Comparator chỉ so score, hai đối tượng có score bằng nhau sẽ được coi là cùng khóa của TreeSet/TreeMap, dù ID khác nhau; dữ liệu có thể bị bỏ/ghi đè ngoài ý muốn. Muốn quản lý nhiều bản ghi theo cùng score, có thể dùng ánh xạ score → danh sách bản ghi, hoặc đưa ID vào khóa nếu logic nghiệp vụ cho phép.

Nếu bài toán yêu cầu **deduplicate**, phải chỉ rõ tiêu chí trùng: cùng ID, cùng email, cùng tất cả thuộc tính hay cùng một tập trường được chọn. Sắp ổn định không tự làm mất phần tử; muốn loại bản ghi trùng cần thêm bước riêng.

### Comparator trả 0 và equals

Comparator trả 0 có nghĩa “tương đương theo thứ tự sắp xếp”, không bắt buộc equals cũng trả true. Tuy nhiên, dùng comparator không nhất quán với equals trong các tập/bản đồ có thứ tự có thể khiến hành vi khác kỳ vọng của mô hình dữ liệu, nên phải xem kỹ hợp đồng cấu trúc được dùng.

## 8. NULL, chữ hoa/thường, dấu tiếng Việt và chuẩn hóa khóa

Trong ứng dụng thực tế, khóa không phải lúc nào cũng là số nguyên hoặc chuỗi ASCII.

### Giá trị null

Nếu một trường có thể là null, phải quy định null đứng trước hay sau. Ví dụ:

~~~java
Comparator<Student> order = Comparator
        .comparing(Student::name,
                   Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Đoạn này cho **name null đứng cuối** khi sắp tên tăng dần. Nó là **mảnh cài đặt minh họa**, không cần thay chương trình đầy đủ ở mục 5 vì ví dụ đó không có null. Nếu đối tượng Student tự nó có thể là null trong danh sách, cần thêm comparator bên ngoài bằng nullsFirst/nullsLast cho **phần tử Student**, khác với null của thuộc tính name.

### Chữ hoa/thường và dấu

**String.compareTo** so sánh theo thứ tự đơn vị UTF-16 của Java, không đồng nghĩa với thứ tự từ điển tiếng Việt mà người dùng mong đợi. Ví dụ tên có dấu hoặc chữ hoa/chữ thường có thể đứng ở vị trí khác khi dùng so sánh mặc định.

Nếu muốn thứ tự ngôn ngữ tự nhiên, cân nhắc **Collator** cho Locale phù hợp, xác định **strength** (có phân biệt dấu hoặc chữ hoa/thường hay không), và cố định lựa chọn này trong quá trình sắp xếp. Khi hai chuỗi được Collator coi là tương đương, một stable sort có thể giữ thứ tự nhập; nếu muốn thứ tự xác định hoàn toàn, bổ sung khóa phá hòa thích hợp.

Không nên tự xóa dấu tiếng Việt hoặc chuyển tất cả chuỗi về chữ thường mà không xác định yêu cầu, vì hành vi chuẩn hóa có thể làm hai khóa vốn khác nhau trở thành bằng nhau và ảnh hưởng cả tìm kiếm lẫn loại trùng.

### Ngày giờ và múi giờ

Với nhiều khóa gồm thời gian, cần phân biệt **Instant** (mốc thời gian tuyệt đối) và **LocalDateTime** (ngày giờ địa phương không có múi giờ). Nếu nghiệp vụ xếp theo thời điểm xảy ra thật, nên quy đổi thống nhất trước khi so. Hai chuỗi thời gian hiển thị tương tự không nhất thiết tương ứng cùng mốc thời gian nếu múi giờ khác.

## 9. Khi nào cần tie-breaker để kết quả có thể tái lập?

Tính ổn định giữ thứ tự gốc, nhưng nếu nguồn có thể đến từ truy vấn, nhiều luồng, nhiều tệp hoặc một API **không cam kết thứ tự ban đầu**, stable sort một mình chưa bảo đảm kết quả giống nhau qua các lần chạy.

Ví dụ trong bảng xếp hạng, hai người có cùng điểm và cùng lớp. Nếu yêu cầu kết quả **luôn giống nhau** bất kể thứ tự đọc từ cơ sở dữ liệu, thêm khóa cuối như **mã học viên duy nhất tăng dần**.

Một thứ tự hoàn toàn xác định nên:

1. So các khóa nghiệp vụ theo đúng mức ưu tiên.
2. So khóa ID ổn định, duy nhất nếu toàn bộ khóa nghiệp vụ bằng nhau.
3. Dùng cùng quy tắc trong mọi lần sắp và trong các hệ thống liên quan.

Nếu đề lại yêu cầu giữ thứ tự đăng ký khi hoàn toàn ngang hạng, **thời điểm đăng ký** hoặc **chỉ số nhập ban đầu** có thể phù hợp hơn ID chữ cái. Không có quy tắc phá hòa phổ quát cho mọi bài.

### Liên hệ với SQL ORDER BY

Một yêu cầu gần tương đương trong SQL có thể là:

~~~sql
SELECT id, team, score, name
FROM students
ORDER BY score DESC, team ASC, name ASC, id ASC;
~~~

Trong ví dụ SQL này, **id ASC** làm kết quả xác định khi ba khóa đầu bằng nhau. Nếu bỏ id và các bản ghi vẫn ngang hạng, thứ tự giữa chúng **không được đảm bảo** chỉ nhờ ORDER BY theo ba khóa. Khi triển khai giữa Java và cơ sở dữ liệu, cần thống nhất quy tắc **NULL**, collation của chuỗi, kiểu dữ liệu và chiều sắp xếp; chúng có thể khác nhau giữa các hệ quản trị.

## 10. Sai lầm phổ biến và cách tránh

1. **Đặt nhầm thứ tự ưu tiên của khóa.** Nếu lớp chỉ là khóa phụ, không được quyết định kết quả theo lớp trước khi so điểm.
2. **Đảo cả comparator bằng reversed() ở cuối.** Lỗi này đổi chiều mọi khóa đã nối, không chỉ khóa chính.
3. **Viết phép trừ để so số nguyên.** Có thể tràn int và làm comparator vi phạm thứ tự.
4. **Dùng sort không ổn định nhưng đòi giữ thứ tự các bản ghi bằng khóa.** Cần chọn thuật toán stable hoặc thêm chỉ số gốc làm khóa cuối trong khi sắp.
5. **Sắp nhiều lượt từ khóa chính sang khóa phụ.** Muốn dùng kỹ thuật stable multi-pass phải đi **từ khóa ít ưu tiên đến khóa ưu tiên nhất**.
6. **Nhầm comparator trả 0 với hai bản ghi giống nhau.** Cùng score không có nghĩa cùng ID, cũng không có nghĩa phải loại trùng.
7. **Dùng Comparator chỉ so một thuộc tính cho TreeSet rồi mất bản ghi khác thuộc tính còn lại.** TreeSet xem compare = 0 là cùng khóa; thiết kế khóa của tập cho đúng.
8. **Không xác định null, hoa/thường và dấu tiếng Việt.** Kết quả có thể khác mong đợi nghiệp vụ hoặc khác giữa Java và cơ sở dữ liệu.
9. **Comparator phụ thuộc trạng thái thay đổi.** Thay đổi điểm hoặc tên trong khi sort làm mất tính nhất quán.
10. **Quên khóa phá hòa trong kết quả cần tái lập.** Stable sort bảo toàn thứ tự hiện có, nhưng không sinh ra một thứ tự nguồn được bảo đảm.
11. **Sửa trực tiếp danh sách không cho phép sửa.** List.of trả danh sách không thể thay đổi cấu trúc; hãy tạo ArrayList trước khi gọi sort như ví dụ.
12. **Không thử trường hợp tất cả khóa bằng nhau.** Đây là ca kiểm thử bộc lộ lỗi ổn định và quy tắc phá hòa.

### Bộ kiểm thử gợi ý

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Mảng/danh sách rỗng | Không lỗi, kết quả rỗng |
| Chỉ một bản ghi | Giữ nguyên bản ghi |
| Tất cả điểm bằng nhau | Khóa lớp rồi tên quyết định kết quả |
| Mọi khóa sắp đều bằng nhau | Stable sort giữ thứ tự gốc |
| Điểm âm, điểm rất lớn | Comparator so đúng, không tràn |
| Hai người cùng tên, khác lớp | Lớp được ưu tiên trước tên |
| Hai bản ghi cùng khóa, khác ID | Có giữ thứ tự nguồn hay phá hòa bằng ID đúng đặc tả |
| Tên có dấu, chữ hoa hoặc null | Dùng quy tắc so sánh/chuẩn hóa đã thống nhất |
| Dữ liệu đã sắp sẵn và đảo ngược | Thuật toán vẫn giữ thứ tự yêu cầu |
| Comparator tùy biến | Kiểm tra phản đối xứng theo dấu và tính bắc cầu |

## 11. Tự kiểm tra

**Câu 1.** Có ba bản ghi (điểm,lớp,tên): (90,B,An), (90,A,Minh), (95,C,An). Sắp theo điểm giảm, lớp tăng, tên tăng thì thứ tự là gì?  
**Đáp án:** (95,C,An), (90,A,Minh), (90,B,An). Điểm quyết định trước; khi điểm bằng nhau mới xét lớp.

**Câu 2.** Với hai bản ghi cùng điểm 90, cùng lớp A và cùng tên An, stable sort có tự chọn ID nhỏ hơn trước không?  
**Đáp án:** Không. Nó giữ thứ tự **đầu vào** của hai bản ghi khi comparator trả 0; cần thêm ID nếu muốn sắp theo ID.

**Câu 3.** Vì sao đảo comparator sau cùng bằng reversed() có thể sai?  
**Đáp án:** Vì đảo **toàn bộ thứ tự nhiều khóa**, kể cả các khóa phụ vốn yêu cầu tăng dần.

**Câu 4.** Khi stable multi-pass với (điểm DESC, lớp ASC, tên ASC), phải sắp theo thứ tự nào?  
**Đáp án:** Tên ASC → lớp ASC → điểm DESC.

**Câu 5.** Có thể dùng TreeSet chỉ so điểm để chứa hai người khác ID nhưng bằng điểm không?  
**Đáp án:** TreeSet xem hai khóa có compare = 0 là cùng một khóa, nên không bảo đảm giữ hai bản ghi riêng biệt. Cần thay thiết kế khóa hoặc dữ liệu lưu.

**Câu 6.** Vì sao stable sort có thể không tạo thứ tự giống hệt giữa hai lần truy vấn cơ sở dữ liệu?  
**Đáp án:** Nếu cơ sở dữ liệu trả các bản ghi ngang hạng theo thứ tự đầu vào khác nhau, stable sort sẽ giữ các thứ tự khác nhau ấy. Thêm khóa cuối duy nhất khi cần kết quả tái lập.

## 12. Ghi nhớ

**Sắp xếp nhiều khóa** là so từ khóa **ưu tiên cao nhất** đến thấp nhất; chỉ khi khóa trước bằng nhau mới xét khóa sau. Mỗi khóa có chiều **ASC/DESC** riêng. **Stable sort** giữ thứ tự gốc của các bản ghi mà comparator coi là ngang hạng; **tie-breaker** tạo ra thứ tự có quy tắc bổ sung khi cần. Trong Java, ưu tiên **Comparator.comparing... → reversed() đúng chỗ → thenComparing...**, dùng **List.sort/Arrays.sort(Object[])** khi cần ổn định, tránh phép trừ so số và xác định rõ cách xử lý khóa lặp, null, chuỗi có dấu và ID.