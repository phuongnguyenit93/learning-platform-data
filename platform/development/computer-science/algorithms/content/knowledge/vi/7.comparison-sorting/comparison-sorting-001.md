# Khóa sắp xếp, bộ so sánh và yêu cầu thứ tự nhất quán

## 1. Sắp xếp phụ thuộc vào một quan hệ thứ tự được đặc tả

Trong thuật toán sắp xếp so sánh, ta không chỉ nói “tăng dần” hoặc “giảm dần” mà phải xác định **khóa sắp xếp** và quy tắc so sánh mọi cặp phần tử. Với bản ghi có nhiều thuộc tính, cùng một danh sách có thể được xếp theo điểm, tên, thời điểm tạo hoặc nhiều tiêu chí kết hợp.

Ví dụ đề bài xếp học viên theo ba tiêu chí:
1. Điểm **giảm dần**.
2. Nếu điểm bằng nhau, tên **tăng dần**, bỏ qua khác biệt hoa/thường; tên không có giá trị (null) đứng cuối nhóm cùng điểm.
3. Nếu điểm và tên vẫn ngang mức, mã học viên **tăng dần**.

Đây là **thứ tự từ điển theo khóa ghép**: so sánh điểm trước, chỉ khi điểm bằng nhau mới so tên, chỉ khi tên ngang mức mới so mã. Không được đảo hướng của tất cả trường chỉ vì một trường cần giảm dần.

Cần phân biệt hai thành phần: **thuật toán sắp xếp** (quicksort, mergesort...) quyết định cách tổ chức phép so sánh/di chuyển; **bộ so sánh** quyết định a đứng trước b, đứng sau b hay bằng b theo yêu cầu của bài toán. Bộ so sánh phải nhất quán thì kết quả mới đáng tin.

## 2. Khóa sắp xếp và khóa ghép

**Khóa sắp xếp (sort key)** là giá trị rút ra từ một phần tử dùng để xác định thứ tự. Ví dụ khóa của số nguyên là giá trị số; khóa của đơn hàng có thể là tổng tiền; khóa của sự kiện có thể là timestamp.

Một khóa ghép chứa nhiều trường theo thứ tự ưu tiên. Với học viên x, có thể mô tả ý tưởng bằng bộ:

\[
K(x)=(-score(x),\ normalizedName(x),\ id(x)).
\]

Dấu âm trong biểu thức chỉ mô tả cách đưa điểm giảm dần về thứ tự tăng dần **trong toán học**. Khi lập trình với số nguyên hữu hạn, phép lấy số đối hoặc trừ hai số có thể tràn; nên sử dụng phương thức so sánh an toàn của Java và đảo comparator thay vì tự đổi dấu.

So sánh từ điển nghĩa là: tại trường đầu tiên mà hai phần tử khác nhau, dùng kết quả so trường đó; nếu tất cả trường bằng nhau thì hai phần tử cùng thứ hạng theo khóa đã chọn. Quy tắc này giúp biến yêu cầu nghiệp vụ thành điều kiện kiểm thử được.

Khóa không nhất thiết chứa mọi thuộc tính. Hai học viên khác mã có thể được coi ngang mức nếu comparator chỉ xét điểm. Điều này hữu ích trong stable sort nhưng có hậu quả khi dùng với TreeSet hoặc TreeMap.

## 3. Ý nghĩa trả về của Comparator trong Java

Giao diện java.util.Comparator<T> định nghĩa phương thức:

~~~java
int compare(T a, T b);
~~~

| Kết quả | Ý nghĩa |
|---|---|
| compare(a,b) nhỏ hơn 0 | a đứng **trước** b |
| compare(a,b) bằng 0 | a và b **ngang mức** theo quan hệ được định nghĩa |
| compare(a,b) lớn hơn 0 | a đứng **sau** b |

Kết quả chỉ cần có **dấu đúng**, không buộc là −1, 0 hoặc 1.

### 3.1. Đối xứng dấu

Đặt sgn(x) là dấu của x: −1, 0 hoặc 1. Bộ so sánh phải thỏa:

\[
sgn(compare(a,b))=-sgn(compare(b,a)).
\]

Nếu a đứng trước b, khi đổi chiều thì b phải đứng sau a. Điều này cũng kéo theo compare(a,a)=0.

### 3.2. Tính bắc cầu

Nếu a đứng sau b, và b đứng sau c, thì a phải đứng sau c:

\[
compare(a,b)>0\ \land\ compare(b,c)>0
\Rightarrow compare(a,c)>0.
\]

Tương tự với quan hệ nhỏ hơn 0. Comparator không được đưa ra một vòng thứ tự kiểu A trước B, B trước C, C trước A. Một quy tắc trò chơi vòng tròn như kéo–búa–bao không phải quan hệ thứ tự phù hợp cho sort.

### 3.3. Nhất quán của nhóm ngang mức

Nếu comparator xem a và b ngang mức thì chúng phải có cùng quan hệ thứ tự với **mọi c**:

\[
compare(a,b)=0
\Rightarrow
sgn(compare(a,c))=sgn(compare(b,c)).
\]

Ví dụ, không thể vừa tuyên bố a ngang mức b, lại tuyên bố a trước c trong khi b sau c. Điều kiện này cùng đối xứng dấu và bắc cầu làm các nhóm ngang mức thành những lớp tương đương có thứ tự nhất quán.

Comparator đúng mô tả một thứ tự toàn phần trên các **lớp tương đương** của những phần tử mà nó so bằng 0. Nếu cần phân biệt tất cả bản ghi, có thể thêm khóa phụ có tính duy nhất; nếu cố ý nhóm theo điểm, các bản ghi có thể so bằng 0 mà vẫn là những đối tượng khác nhau.

### 3.4. “Nhất quán với equals” là yêu cầu bổ sung

Hợp đồng Comparator không bắt buộc compare(a,b)==0 tương đương a.equals(b). Ví dụ hai học viên khác mã cùng điểm 90: comparator chỉ xét điểm trả 0, còn equals của record có thể trả false.

Khi sắp xếp List, điều đó có thể đúng ý định vì hai phần tử ngang hạng. Nhưng TreeSet/TreeMap dùng **so sánh bằng 0** để xác định phần tử hoặc khóa trùng; chúng có thể gộp hai đối tượng mà equals cho là khác nhau. Vì vậy, trước khi dùng comparator trong tập/bản đồ có thứ tự, phải xác định rõ cách nhận diện phần tử/khóa.

**Phân biệt:** một comparator có thể **nhất quán về thứ tự** nhưng **không nhất quán với equals**. Đây là hai khái niệm khác nhau.

## 4. Comparable và Comparator: chọn công cụ

**Comparable<T>**: lớp cung cấp thứ tự tự nhiên qua compareTo. Integer, Long, String có thứ tự tự nhiên. Thích hợp khi bản thân kiểu có một thứ tự mặc định rõ ràng.

**Comparator<T>**: đối tượng mô tả một cách so sánh độc lập. Cùng một lớp Student có thể có comparator theo điểm, theo tên, theo mã hoặc khóa ghép. Dùng khi gọi List.sort, Collections.sort, Arrays.sort cho đối tượng, hoặc khi tạo TreeSet/TreeMap.

Java 17 có các phương thức hỗ trợ:

| API | Tác dụng |
|---|---|
| Comparator.comparing(Student::name) | So theo khóa tham chiếu có thứ tự tự nhiên |
| Comparator.comparingInt(Student::score) | So khóa int mà không cần boxing |
| thenComparing(...) | Dùng tiêu chí phụ nếu tiêu chí trước ngang mức |
| reversed() | Đảo hướng của toàn comparator hiện tại |
| Comparator.nullsFirst(...) / nullsLast(...) | Quy định vị trí giá trị null |
| Comparator.naturalOrder() / reverseOrder() | Dùng thứ tự tự nhiên hoặc đảo thứ tự |
| String.CASE_INSENSITIVE_ORDER | So chuỗi không phân biệt chữ hoa/thường theo quy tắc tích hợp |

Để điểm **giảm** nhưng tên **tăng**, đảo chỉ comparator của điểm, rồi mới nối comparator tên:

~~~java
Comparator<Student> ranking =
        Comparator.comparingInt(Student::score).reversed()
                .thenComparing(Student::name,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))
                .thenComparingInt(Student::id);
~~~

Nếu gọi reversed() ở **cuối toàn chuỗi**, cả điểm, tên và id đều đảo. Đặc biệt, nullsLast của tiêu chí tên cũng có thể bị đảo thành nullsFirst. Đặt reversed() đúng vị trí là một phần của việc triển khai hợp đồng.

Comparator.nullsLast ở ví dụ trên xử lý **trường name null**, không có nghĩa danh sách được phép chứa Student null. Nếu bản thân phần tử Student có thể null, phải bọc comparator của **toàn phần tử** bằng Comparator.nullsLast hoặc nullsFirst phù hợp.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu dưới tên **SortingComparatorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class SortingComparatorDemo {
    private SortingComparatorDemo() {
    }

    record Student(int id, String name, int score) {
    }

    private static List<Integer> ids(List<Student> students) {
        return students.stream().map(Student::id).toList();
    }

    public static void main(String[] args) {
        List<Student> source = List.of(
                new Student(31, "Lan", 90),
                new Student(12, "An", 95),
                new Student(23, null, 90),
                new Student(17, "Binh", 95),
                new Student(18, "an", 95),
                new Student(44, "Minh", 90)
        );

        // Điểm giảm, tên tăng không phân biệt hoa/thường,
        // tên null cuối; cuối cùng dùng mã tăng.
        Comparator<Student> byRanking =
                Comparator.comparingInt(Student::score).reversed()
                        .thenComparing(Student::name,
                                Comparator.nullsLast(
                                        String.CASE_INSENSITIVE_ORDER))
                        .thenComparingInt(Student::id);

        List<Student> ranking = new ArrayList<>(source);
        ranking.sort(byRanking);
        System.out.println("Ranking ids: " + ids(ranking));

        // Java List.sort là stable sort: bằng điểm giữ nguyên thứ tự nguồn.
        List<Student> stable = new ArrayList<>(source);
        stable.sort(Comparator.comparingInt(Student::score).reversed());
        System.out.println("Stable score-only ids: " + ids(stable));

        // TreeSet dùng compare==0 để phát hiện phần tử cùng khóa.
        Set<Student> byScore =
                new TreeSet<>(Comparator.comparingInt(Student::score));
        byScore.add(new Student(1, "A", 90));
        byScore.add(new Student(2, "B", 90));
        System.out.println("TreeSet by score size: " + byScore.size());

        // Trừ hai int có thể tràn số và đảo ngược dấu.
        System.out.println("Safe integer compare: "
                + Integer.compare(Integer.MAX_VALUE, -1));
        System.out.println("Unsafe subtraction: "
                + (Integer.MAX_VALUE - (-1)));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SortingComparatorDemo.java
java SortingComparatorDemo
~~~

Stdout chính xác:

~~~text
Ranking ids: [12, 18, 17, 31, 44, 23]
Stable score-only ids: [12, 17, 18, 31, 23, 44]
TreeSet by score size: 1
Safe integer compare: 1
Unsafe subtraction: -2147483648
~~~

**Giải thích kết quả:**
- Nhóm 95 đứng trước nhóm 90. Trong nhóm 95, An và an ngang mức theo CASE_INSENSITIVE_ORDER, nên id 12 đứng trước id 18; Binh theo sau. Trong nhóm 90, Lan rồi Minh rồi tên null.
- Khi chỉ so theo điểm, stable sort giữ thứ tự gốc của các phần tử cùng điểm: nhóm 95 vẫn 12,17,18 và nhóm 90 vẫn 31,23,44.
- TreeSet chỉ xét điểm coi hai học viên đều điểm 90 là cùng khóa, nên size bằng 1; hai đối tượng vẫn có id và name khác nhau.
- Integer.MAX_VALUE − (−1) vượt miền int 32 bit, tạo giá trị âm. Integer.compare trả dấu đúng. Với long dùng Long.compare thay vì phép trừ.

Mã dùng List.of chứa các **đối tượng Student không null**; trường name bên trong một đối tượng được phép null. List.of tạo danh sách không thể thay đổi cấu trúc, vì thế cần tạo ArrayList mới trước khi gọi sort.

## 6. Stable sort: xử lý thứ tự giữa các phần tử bằng khóa

Một phép sắp xếp gọi là **ổn định (stable)** nếu những phần tử được comparator so bằng 0 **giữ nguyên thứ tự tương đối** như trong đầu vào.

Ví dụ đầu vào A(80), B(90), C(80), sắp điểm tăng dần ổn định tạo [A,C,B]: A và C cùng điểm, A vẫn đứng trước C. Phép sắp xếp không ổn định có thể đặt C trước A.

Khi nào cần stable sort?
- Nếu đề yêu cầu nhóm phần tử cùng khóa giữ nguyên thứ tự nhận dữ liệu, cần phép sort ổn định và comparator chỉ xét đúng các khóa đã được yêu cầu.
- Nếu cần thứ tự đầu ra **không phụ thuộc thứ tự đầu vào**, một khóa phụ duy nhất như id có thể tạo một thứ tự xác định. Nhưng bổ sung id có thể **làm sai** yêu cầu giữ thứ tự nhận ban đầu nếu id không cùng thứ tự.
- Nếu muốn sắp xếp hai lần bằng stable sort, hãy sắp theo **tiêu chí phụ trước, tiêu chí chính sau**. Khi sắp theo chính, thứ tự phụ bên trong nhóm bằng nhau vẫn được bảo toàn.

Trong Java, List.sort và Arrays.sort đối với **mảng đối tượng** được đặc tả là stable. Không nên suy ra một thuật toán sort tùy ý cũng ổn định; cần kiểm tra hợp đồng và triển khai. Với mảng nguyên thủy, không có danh tính bản ghi riêng gắn với các giá trị bằng nhau để quan sát tính ổn định theo cách thông thường.

**Stable không đồng nghĩa deterministic giữa mọi hoán vị đầu vào.** Nó bảo toàn thứ tự ngang khóa của **chính đầu vào đang xét**. Nếu hoán vị đầu vào thay đổi, thứ tự các phần tử cùng khóa trong kết quả cũng có thể thay đổi.

## 7. Những lỗi so sánh thường gặp

### 7.1. Dùng phép trừ int hoặc lấy số đối

~~~java
// Sai với một số cặp int vì có thể tràn:
Comparator<Integer> broken = (a, b) -> a - b;

// Đúng:
Comparator<Integer> safe = Integer::compare;
~~~

Trường hợp a=MAX_VALUE, b=−1 đã minh họa phép trừ tràn làm dấu bị đảo. Các so sánh long cũng nên dùng Long.compare.

### 7.2. Comparator không bắc cầu

Nếu A trước B, B trước C mà C trước A, quan hệ có chu trình, không thể sắp thành một thứ tự nhất quán. Một số triển khai sort của Java có thể phát hiện hợp đồng bị vi phạm và ném IllegalArgumentException; ở trường hợp khác có thể cho kết quả khó dự đoán. Việc một lần sort chạy xong **không chứng minh** comparator đúng cho mọi đầu vào.

### 7.3. Khóa thay đổi trong lúc sort

Nếu comparator đọc giá, thời điểm hoặc trạng thái mà luồng khác liên tục thay đổi, cùng một cặp có thể nhận kết quả so sánh khác nhau trong một lần chạy. Với dữ liệu biến động, nên cố định phiên bản dữ liệu hoặc tiền tính khóa trên một ảnh chụp ổn định trước khi sắp xếp.

### 7.4. Dùng reversed sai phạm vi

~~~java
// Đảo cả điểm và tên: không đúng nếu chỉ điểm cần giảm.
Comparator<Student> wrong =
        Comparator.comparingInt(Student::score)
                .thenComparing(Student::name,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))
                .reversed();

// Chỉ đảo tiêu chí điểm:
Comparator<Student> correct =
        Comparator.comparingInt(Student::score).reversed()
                .thenComparing(Student::name,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
~~~

### 7.5. Nhầm compare==0 với equals

Record Student mặc định xét tất cả trường trong equals, nhưng comparator chỉ xét score có thể cho 0 dù hai Student khác id. Đây có thể là điều đúng khi **xếp nhóm** nhưng tạo kết quả không mong muốn trong TreeSet/TreeMap nếu muốn lưu hai khóa khác nhau.

### 7.6. Bỏ quên null và giá trị đặc biệt

Comparator.comparing(Student::name) sẽ không tự xử lý null. Quy định rõ null đứng đầu, cuối hoặc là đầu vào không hợp lệ. Khi dùng float/double phải quyết định cách xử lý NaN, +0.0, −0.0 và vô cực; Double.compare/Float.compare có hợp đồng xác định trong Java, còn so sánh tùy tiện kiểu “nếu a>b thì trả 1, còn lại trả −1” có thể sai ngay với a=b hoặc NaN.

## 8. Chuỗi tiếng Việt, Locale và chi phí trích xuất khóa

String.compareTo so các chuỗi theo quy tắc thứ tự đơn vị UTF-16 của String, không phải từ điển tiếng Việt có xét dấu theo quy tắc địa phương. String.CASE_INSENSITIVE_ORDER chỉ giải quyết nhu cầu so không phân biệt hoa/thường theo quy tắc được tích hợp; nó **không đồng nghĩa** sắp xếp tên tiếng Việt theo chuẩn ngôn ngữ.

Khi cần phân loại theo ngôn ngữ, có thể sử dụng java.text.Collator với Locale và mức so sánh được cấu hình, rồi kiểm thử chuỗi có dấu, chữ hoa/thường và các trường hợp đặc biệt theo hợp đồng sản phẩm. Locale và mức độ mạnh của Collator là một phần của chính sách sort, nên cần cố định chúng để đầu ra ổn định giữa các môi trường.

Comparator.comparing có thể gọi hàm trích xuất khóa nhiều lần trong n log n lần so sánh. Nếu mỗi lần trích xuất phải phân tích một tài liệu lớn, đọc đĩa hoặc gọi dịch vụ mạng, tổng thời gian có thể tăng mạnh và khóa có thể biến động. Với khóa tốn công và dữ liệu tĩnh, hãy **tiền tính khóa**, giữ khóa cùng đối tượng trong một cấu trúc trung gian, sắp theo khóa đã tính và ánh xạ trở lại bản ghi.

Comparator nên là phép so sánh **thuần**, không sửa dữ liệu, không phụ thuộc thứ tự gọi và không có tác dụng phụ quan trọng. Những thuộc tính này giúp dễ chứng minh và kiểm thử.

## 9. Độ phức tạp khi dùng comparator

Với n phần tử có khóa phân biệt, thuật toán sắp xếp dựa vào các phép so sánh có chặn dưới Ω(n log n) phép so sánh trong trường hợp xấu nhất theo mô hình cây quyết định. Một thuật toán so sánh có bảo đảm O(n log n), chẳng hạn mergesort, đạt bậc chặt Θ(n log n) theo số phép so sánh trong mô hình chung; các triển khai khác có thể có thời gian xấu nhất O(n²).

Nếu mỗi lần compare tốn O(1), thời gian sort tỉ lệ theo số phép so sánh cộng chi phí di chuyển dữ liệu. Với khóa chuỗi dài tối đa L ký tự, mỗi phép so sánh từ điển có thể mất O(L) ở trường hợp xấu. Nếu có m tiêu chí ghép, có thể cần xét tới m tiêu chí cho một cặp; chi phí comparator không nên bị bỏ qua.

**Số phép so sánh và tính đúng là hai vấn đề khác nhau.** Thuật toán dù nhanh vẫn có thể cho kết quả không hợp lệ nếu comparator vi phạm tính bắc cầu hoặc quy tắc bằng nhau.

## 10. Kiểm thử hợp đồng comparator và kết quả

Bộ kiểm thử nên gồm cả giá trị thường, giá trị biên, phần tử bằng khóa và nhiều cách sắp xếp thứ tự đầu vào:

| Dữ liệu | Điều cần kiểm tra |
|---|---|
| Điểm khác nhau | Điểm cao đứng trước |
| Điểm bằng, tên khác | Áp dụng chính xác thứ tự tên |
| Tên cùng chữ khác hoa/thường | Đi tới tiêu chí phụ id nếu tên ngang mức |
| Tên null và không null | Đúng quy tắc nullsLast trong nhóm cùng điểm |
| Cùng điểm và tên, id khác | Mã tăng dần nếu là khóa phụ cuối |
| Integer.MIN_VALUE và MAX_VALUE | Không có so sánh sai do tràn phép trừ |
| Hai đối tượng khác nhau nhưng cùng score | Stable sort giữ thứ tự nếu comparator chỉ so score |
| Hai đối tượng cùng score trong TreeSet | Biết rõ một phần tử có thể bị xem là trùng khóa |

Kiểm tra tính chất trên tập ví dụ nhỏ, bằng nhiều cặp hoặc bộ ba phần tử:
1. Với mọi a,b, dấu compare(a,b) đối xứng ngược với dấu compare(b,a); compare(a,a)==0.
2. Nếu compare(a,b)>0 và compare(b,c)>0, phải có compare(a,c)>0.
3. Nếu compare(a,b)==0, dấu compare(a,c) phải bằng dấu compare(b,c) với mọi c.
4. Sau sort, các cặp phần tử liên tiếp trong kết quả phải thỏa compare(result[i],result[i+1])<=0. Điều này cần thiết nhưng **chưa đủ** để chứng minh comparator đúng cho mọi đầu vào.

Với hệ thống thực, kiểm thử thêm thay đổi thứ tự đầu vào, giá trị null, chuỗi Unicode, cùng khóa ở nhiều bản ghi và dữ liệu lớn. Nếu đầu ra phải tái lập bất kể thứ tự nguồn, kiểm tra các khóa phụ đã phân biệt đúng những phần tử mà nghiệp vụ yêu cầu.

## 11. Tự kiểm tra

**Câu 1.** Hai học viên khác id nhưng cùng điểm. Comparator chỉ xét điểm trả 0 có sai không?  
**Đáp án:** Không tự động sai; đây là nhóm ngang điểm hợp lệ. Tuy nhiên TreeSet theo comparator này có thể chỉ giữ một trong hai. Muốn phân biệt học viên cần khóa phụ đúng yêu cầu.

**Câu 2.** Đề yêu cầu điểm giảm, tên tăng. Vì sao gọi reversed() sau thenComparing(name) dễ sai?  
**Đáp án:** Nó đảo **cả** điểm và tên. Đảo comparator điểm trước, rồi mới nối tên tăng.

**Câu 3.** Tại sao không dùng a−b để so hai int?  
**Đáp án:** Có thể tràn số nguyên và trả dấu trái quan hệ thứ tự. Dùng Integer.compare.

**Câu 4.** Stable sort có bảo đảm một thứ tự tuyệt đối cho các phần tử cùng khóa không?  
**Đáp án:** Không. Stable chỉ giữ **thứ tự tương đối từ đầu vào**. Muốn thứ tự độc lập đầu vào phải bổ sung khóa phụ thích hợp nếu hợp đồng cho phép.

**Câu 5.** Nếu compare(a,b)=0, compare(a,c)<0 nhưng compare(b,c)>0, điều gì sai?  
**Đáp án:** Tính nhất quán của nhóm ngang mức bị vi phạm. Phải sửa bộ so sánh trước khi sắp xếp.

**Ghi nhớ:** Xác định rõ **khóa chính/phụ, hướng tăng giảm, chính sách null, nhóm bằng khóa, tính ổn định và quan hệ với equals**. Bộ so sánh đúng là nền tảng để thuật toán sắp xếp cho kết quả chính xác, tái lập và có thể kiểm chứng.
