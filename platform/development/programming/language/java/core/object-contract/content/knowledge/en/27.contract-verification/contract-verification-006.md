# Kiểm thử bộ ba cho `compareTo()` và `Comparator`

## Mục tiêu và phạm vi

Một phép so sánh có vẻ đúng khi thử riêng hai giá trị vẫn có thể **sai khi xét ba giá trị**. Bài này hướng dẫn kiểm chứng hợp đồng sắp thứ tự của `Comparable.compareTo()` và `Comparator.compare()` trong Java: đối dấu khi đảo hai toán hạng, tính bắc cầu, và tính nhất quán của những giá trị được coi là bằng nhau theo thứ tự. Trọng tâm là cách tạo và kiểm thử các **bộ ba `(a, b, c)`**, tìm phản ví dụ, rồi sửa bộ so sánh để các thao tác sort, `TreeSet` và `TreeMap` hoạt động có thể dự đoán.

Các kiểm thử ở đây kiểm chứng **hợp đồng thứ tự**, không thay thế kiểm thử `equals()`/`hashCode()`; tuy vậy phải hiểu quan hệ giữa `compare(x, y) == 0` và `equals()` khi dùng tập hoặc map có sắp xếp.

## 1. Hiểu đúng kết quả so sánh

Với hai đối tượng `x`, `y`:

- `x.compareTo(y) < 0` hoặc `comparator.compare(x, y) < 0`: `x` đứng trước `y`.
- Kết quả bằng `0`: `x` và `y` **tương đương theo thứ tự** đang xét.
- Kết quả `> 0`: `x` đứng sau `y`.

Hợp đồng **chỉ quy định dấu**, không bắt trả về chính xác `-1`, `0` hay `1`. Vì vậy các phép thử nên chuẩn hóa với `Integer.signum(result)`, tránh viết `compare(x, y) == -1` hoặc lấy số đối của kết quả thô (có thể tràn số khi kết quả là `Integer.MIN_VALUE`).

`Comparable<T>` định nghĩa **thứ tự tự nhiên** của một kiểu thông qua `compareTo(T other)`. `Comparator<T>` cho phép định nghĩa thứ tự bên ngoài đối tượng, như sắp `Person` theo tuổi, rồi theo mã. Hai cơ chế có cùng các quy tắc kiểm chứng quan trọng dưới đây. Một `Comparator` có thể chấp nhận `null` nếu chủ động định nghĩa cách xử lý; `compareTo(null)` của đối tượng khác `null` phải ném `NullPointerException` theo hợp đồng `Comparable`.

Ký hiệu dùng trong bài: `c(x,y)` là kết quả `x.compareTo(y)` hoặc `comparator.compare(x,y)`; `sgn(v)` là dấu của số nguyên `v`.

## 2. Ba nhóm điều kiện phải kiểm chứng

### 2.1. Đảo toán hạng: cặp `(a, b)`

Với mọi phần tử thuộc miền so sánh hợp lệ:

```text
sgn(c(a,b)) == -sgn(c(b,a))
c(a,a) == 0
```

Nếu `a < b` thì chiều ngược lại phải là `b > a`. Nếu `a` và `b` được xem là cùng vị trí (`c(a,b)==0`) thì chiều ngược lại cũng bằng `0`. Kiểm tra `c(a,a)==0` là phép thử đơn giản, bổ trợ cho tính đối dấu.

**Lỗi dễ gặp:** dùng `return a - b;` với số nguyên; phép trừ có thể tràn và làm hai chiều đều âm. Hãy dùng `Integer.compare(a,b)`, `Long.compare(a,b)` hoặc `Comparator.comparingInt(...)` tùy ngữ cảnh.

### 2.2. Bắc cầu: bộ ba `(a, b, c)`

Nếu `a > b` và `b > c`, bắt buộc `a > c`; tương tự với chiều nhỏ hơn:

```text
c(a,b) > 0  &&  c(b,c) > 0   =>   c(a,c) > 0
c(a,b) < 0  &&  c(b,c) < 0   =>   c(a,c) < 0
```

Đây là lý do cần **kiểm thử bộ ba**: kiểm tra mỗi cặp đơn lẻ không phát hiện được vòng mâu thuẫn.

Ví dụ bộ so sánh tùy biến mô tả vòng `0 < 1`, `1 < 2`, nhưng `2 < 0`. Mỗi cặp đều có một chiều trước/sau rõ ràng và đối dấu đúng. Tuy nhiên bộ ba `(0,1,2)` chứng minh sai: từ `0 < 1` và `1 < 2` phải suy ra `0 < 2`, trái với kết quả `0 > 2`. Một bộ so sánh như vậy không tạo ra thứ tự nhất quán.

### 2.3. Bằng 0 phải nhất quán với phần tử thứ ba

Nếu `a` và `b` được xem là tương đương theo thứ tự, thì đối với **mọi `c`** chúng phải có cùng quan hệ đứng trước/đứng sau/đồng hạng:

```text
c(a,b) == 0  =>  sgn(c(a,c)) == sgn(c(b,c))
```

Kết hợp với quy tắc đảo toán hạng, quan hệ này cũng đúng khi phần tử thứ ba đứng ở phía bên trái. Nó bảo đảm các nhóm đồng hạng (`compare == 0`) hành xử như các lớp tương đương hợp lệ; chẳng hạn nếu `a ~ b` và `b ~ c`, thì `a ~ c`.

Phản ví dụ: bộ so sánh coi `0` và `2` là bằng nhau, nhưng những cặp còn lại so theo thứ tự số nguyên. Khi xét `(a,b,c)=(0,2,1)`, ta có `c(0,2)==0`, nhưng `c(0,1)<0` trong khi `c(2,1)>0`. Nhóm đồng hạng này không nhất quán. Kiểm thử chỉ tính bắc cầu ở các cặp **so sánh khác 0** là chưa đủ để giải thích toàn bộ hợp đồng.

## 3. Viết bộ kiểm chứng độc lập bằng Java 17+

Ví dụ hoàn chỉnh dưới đây duyệt toàn bộ cặp và bộ ba trên một tập mẫu nhỏ. Nó dùng **cùng một hàm kiểm chứng** cho cả `compareTo()` (truyền method reference) lẫn `Comparator`. Bốn tình huống thể hiện hai thứ tự đúng và hai thứ tự cố ý sai.

```java
// OrderingTriplesDemo.java
import java.util.Comparator;
import java.util.List;

public final class OrderingTriplesDemo {
    private static int sign(int value) {
        return Integer.signum(value);
    }

    private static <T> void checkContract(
            List<T> samples, Comparator<? super T> comparator) {

        // Kiểm tra phản xạ và tính đối dấu trên mọi cặp.
        for (T a : samples) {
            if (sign(comparator.compare(a, a)) != 0) {
                throw new AssertionError("reflexivity");
            }
            for (T b : samples) {
                int ab = sign(comparator.compare(a, b));
                int ba = sign(comparator.compare(b, a));
                if (ab != -ba) {
                    throw new AssertionError("opposite signs");
                }
            }
        }

        // Kiểm tra mọi bộ ba có thứ tự (a, b, c).
        for (T a : samples) {
            for (T b : samples) {
                for (T c : samples) {
                    int ab = sign(comparator.compare(a, b));
                    int bc = sign(comparator.compare(b, c));
                    int ac = sign(comparator.compare(a, c));

                    if (ab == 0 &&
                            ac != sign(comparator.compare(b, c))) {
                        throw new AssertionError("zero-class consistency");
                    }
                    if ((ab > 0 && bc > 0 && ac <= 0) ||
                            (ab < 0 && bc < 0 && ac >= 0)) {
                        throw new AssertionError("transitivity");
                    }
                }
            }
        }
    }

    private static void run(
            String label, List<Integer> samples,
            Comparator<Integer> comparator) {
        try {
            checkContract(samples, comparator);
            System.out.println(label + ": PASS");
        } catch (AssertionError error) {
            System.out.println(label + ": FAIL - " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        Comparator<Integer> byAbsoluteValue =
                Comparator.comparingLong(x -> Math.abs((long) x));

        // Phản ví dụ 1: 0 < 1 < 2 < 0, vi phạm bắc cầu.
        Comparator<Integer> cyclic = (a, b) -> {
            if (a.equals(b)) {
                return 0;
            }
            return (a + 1) % 3 == b ? -1 : 1;
        };

        // Phản ví dụ 2: coi 0 ~ 2 nhưng so cặp khác theo số học.
        Comparator<Integer> merged = (a, b) -> {
            if ((a == 0 && b == 2) || (a == 2 && b == 0)) {
                return 0;
            }
            return Integer.compare(a, b);
        };

        run("Integer.compareTo", List.of(-2, -1, 0, 1, 2),
                Integer::compareTo);
        run("Comparator abs", List.of(-2, -1, 0, 1, 2),
                byAbsoluteValue);
        run("Comparator cycle", List.of(0, 1, 2), cyclic);
        run("Comparator merged", List.of(0, 2, 1), merged);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 OrderingTriplesDemo.java
java OrderingTriplesDemo
```

Đầu ra chính xác:

```text
Integer.compareTo: PASS
Comparator abs: PASS
Comparator cycle: FAIL - transitivity
Comparator merged: FAIL - zero-class consistency
```

**Cách đọc kết quả:**

- `Integer::compareTo` dùng thứ tự tự nhiên, nên vượt qua các mẫu kiểm thử.
- So sánh theo trị tuyệt đối tạo ra nhóm `-2 ~ 2`, `-1 ~ 1`. Đây vẫn là thứ tự hợp lệ: các phần tử bằng nhau theo trị tuyệt đối có quan hệ giống nhau với mọi phần tử thứ ba. Nhóm đồng hạng **không buộc** các đối tượng phải `equals()`.
- `cyclic` giữ tính đối dấu cho từng cặp nhưng tạo chu trình so sánh.
- `merged` coi `0` và `2` đồng hạng không đúng cách; chọn thứ tự mẫu `[0,2,1]` để bộ kiểm tra đưa ra phản ví dụ `zero-class consistency` trước các dạng vi phạm khác.

Các comparator `cyclic` và `merged` **chỉ dùng để minh họa lỗi**, không sử dụng để sắp xếp dữ liệu thực. Hàm `checkContract` kiểm tra hữu hạn các mẫu, nên `PASS` không chứng minh đúng với mọi giá trị có thể có; cần cả lập luận về logic sắp thứ tự và tập test đại diện.

## 4. Phân biệt tính nhất quán với `equals()`

Hợp đồng trên không yêu cầu `compare(a,b)==0` luôn đồng nghĩa `a.equals(b)`: đây là khuyến nghị rất mạnh của `Comparable` và điều cần xét cho `Comparator`, **không phải yêu cầu bắt buộc trong mọi thiết kế thứ tự**. Một bộ so sánh theo độ dài chuỗi, theo tuổi hoặc trị tuyệt đối có thể hợp lệ mà vẫn nhóm nhiều đối tượng `equals()` khác nhau vào một vị trí.

Tuy nhiên `TreeSet` và `TreeMap` dùng **kết quả comparator hoặc `compareTo` để quyết định tính trùng khóa/phần tử**. Vì thế khi comparator trả về 0 cho hai đối tượng khác nhau, collection có thể giữ một phần tử hay một entry cho cả hai khóa. Đây không phải lỗi của collection mà là hệ quả của thứ tự đã chọn.

Ví dụ Java 17+:

```java
// TreeSetOrderingDemo.java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetOrderingDemo {
    record Member(int age, String code) {}

    public static void main(String[] args) {
        Member a = new Member(30, "A");
        Member b = new Member(30, "B");

        Comparator<Member> byAge =
                Comparator.comparingInt(Member::age);
        Set<Member> onlyAge = new TreeSet<>(byAge);
        onlyAge.add(a);
        onlyAge.add(b);

        Comparator<Member> byAgeThenCode = byAge
                .thenComparing(Member::code);
        Set<Member> ageAndCode = new TreeSet<>(byAgeThenCode);
        ageAndCode.add(a);
        ageAndCode.add(b);

        System.out.println(a.equals(b));
        System.out.println(onlyAge.size());
        System.out.println(ageAndCode.size());
    }
}
```

```bash
javac TreeSetOrderingDemo.java
java TreeSetOrderingDemo
```

```text
false
1
2
```

`record Member` có `equals()` xét cả tuổi và mã. Comparator chỉ theo tuổi coi hai phần tử đồng hạng; comparator có `thenComparing(Member::code)` dùng thêm tiêu chí phân biệt. Phải chọn khóa và tiêu chí phụ theo yêu cầu nghiệp vụ: đôi khi cố ý gộp nhiều phần tử là đúng, nhưng phải biết rõ tác động lên cấu trúc có sắp xếp.

## 5. Cách chọn bộ ba để kiểm thử có giá trị

Một tập dữ liệu thử nên gồm **nhiều lớp tương đương, điểm biên và những giá trị dễ tạo mâu thuẫn**. Chọn không chỉ các chuỗi tăng đều `(1,2,3)` mà cả bộ ba có một hoặc nhiều cặp `compare==0`.

| Nhóm mẫu | Ví dụ | Vấn đề cần bắt |
| --- | --- | --- |
| Ba phần tử khác nhau | `(a,b,c)` với `a<b<c` và mọi hoán vị | Bắc cầu ở cả hai hướng, vòng so sánh |
| Hai phần tử đồng hạng | `compare(a,b)==0` nhưng `a` và `b` là hai đối tượng khác nhau | Quan hệ với `c` phải giống nhau |
| Ba phần tử đồng hạng | `a~b`, `b~c` | Tính bắc cầu của lớp đồng hạng |
| Biên số nguyên | `Integer.MIN_VALUE`, `-1`, `0`, `Integer.MAX_VALUE` | Tràn số khi trừ, đổi dấu `MIN_VALUE` |
| Nhiều khóa sắp xếp | Cùng điểm, khác tuổi/mã; hoặc cùng khóa chính và khóa phụ | `thenComparing`, xử lý tie |
| Chuỗi, chữ hoa/thường | `"a"`, `"A"`, chuỗi rỗng, chữ có dấu | Chuẩn hóa, locale, phép so sánh có tính bắc cầu |
| `null` (nếu comparator hỗ trợ) | `(null,a,b)` | Chính sách `nullsFirst`/`nullsLast` nhất quán |
| Số thực | `-0.0`, `+0.0`, `NaN`, vô cực | Ngữ nghĩa của `Double.compare` khác các phép toán `<`/`>` thông thường |

Khi kiểm thử `Comparable`, chỉ tạo bộ ba gồm các đối tượng thực sự có thể so sánh theo hợp đồng kiểu dữ liệu. Khi kiểm thử một comparator có thể ném exception theo thiết kế với một số input, tách rõ nhóm input hợp lệ và trường hợp phải ném lỗi. Không “sửa” phép kiểm bằng cách nuốt mọi exception rồi đánh dấu PASS.

### Quy trình thực hành

1. **Xác định miền hợp lệ và chính sách tie:** trường nào được so sánh, có cho `null` không, comparator có được nhóm đối tượng khác `equals()` không.
2. **Kiểm tra từng cặp:** `c(a,a)==0`; hai chiều có dấu đối nhau. Dùng `signum`, không so khớp giá trị trả về cụ thể.
3. **Kiểm tra mọi bộ ba có thứ tự:** cả hai hướng bắc cầu và trường hợp `c(a,b)==0`. Không chỉ kiểm tra một cách sắp `(a,b,c)`: đổi vị trí có thể làm lộ lỗi mới.
4. **Giữ lại bộ ba phản ví dụ tối giản:** ghi ba giá trị đầu vào, dấu `c(a,b)`, `c(b,c)`, `c(a,c)` và lý do sai. Điều này giúp sửa điều kiện so sánh chính xác.
5. **Bổ sung phép thử dài hạn:** khi thêm một trường vào `compareTo`, đổi comparator, hoặc thay đổi chính sách `null`, chạy lại test với tập mẫu biên và các trường hợp từng gây lỗi.

Với `n` phần tử mẫu, kiểm tra mọi cặp cần khoảng `O(n²)` phép thử, mọi bộ ba cần `O(n³)` lần duyệt. Thích hợp để chạy đầy đủ trên **tập mẫu nhỏ có chọn lọc**. Với miền lớn, có thể phát sinh nhiều bộ ba ngẫu nhiên bằng seed cố định và sử dụng property-based testing; khi có lỗi, thu nhỏ (shrink) về bộ ba dễ hiểu. Phương pháp ngẫu nhiên là bổ sung, không thay thế các mẫu biên hay lập luận về tính đúng đắn.

## 6. Những cách viết comparator dễ phá hợp đồng

### Dùng phép trừ thay `Integer.compare`

```java
// Sai khi tràn int:
Comparator<Integer> unsafe = (a, b) -> a - b;

// An toàn với toàn miền int:
Comparator<Integer> safe = Integer::compare;
```

Với `a = Integer.MAX_VALUE`, `b = -1`, cả `a-b` và `b-a` đều có thể nhận `Integer.MIN_VALUE` vì tràn số; hai chiều cùng âm, vi phạm đối dấu. Đừng dùng `Math.abs(a-b)` hay lấy `-compare(b,a)` trực tiếp để xác định dấu kỳ vọng.

### Lắp ghép quy tắc ưu tiên tạo vòng

Các câu điều kiện kiểu “A ưu tiên B, B ưu tiên C, C ưu tiên A” có thể thỏa mãn mọi kiểm thử cặp và vẫn phá bắc cầu. Nếu thứ tự nghiệp vụ thực sự tuần hoàn, nó **không thích hợp làm Comparator** cho một thứ tự tổng quát. Cần mô hình hóa luật xếp lịch/ưu tiên dưới dạng quan hệ riêng, hoặc chọn một khóa có thứ tự toàn phần để sort.

### Trả về 0 tùy tiện cho “không biết so thế nào”

`0` phải biểu thị cùng hạng theo quan hệ thứ tự nhất quán, **không có nghĩa là bỏ qua phép so sánh**. Nếu chỉ đôi lúc trả 0 cho hai giá trị để “tránh xử lý”, bộ ba với phần tử thứ ba có thể mâu thuẫn. Hãy định nghĩa tiêu chí phụ hợp lệ hoặc chính sách cho input không thể so sánh.

### Phụ thuộc trạng thái thay đổi theo thời gian

Nếu comparator đọc `System.currentTimeMillis()`, `Random`, dữ liệu có thể thay đổi, hoặc trường mutable bị chỉnh trong lúc phần tử đang nằm trong `TreeSet`/`TreeMap`, hai lần so sánh cùng cặp có thể cho kết quả khác nhau. Các phép kiểm bộ ba giả định **cùng trạng thái so sánh ổn định**. Nên sắp theo khóa bất biến, tạo snapshot, hoặc xây lại collection khi khóa ảnh hưởng thứ tự đã thay đổi.

### Thiếu tiêu chí phụ hoặc xử lý kiểu đặc biệt

Với sắp xếp nhiều khóa, dùng `Comparator.comparing(...).thenComparing(...)` để tạo thứ tự từ các phép so sánh hợp lệ. Với số thực, dùng `Double.compare` hoặc `comparingDouble` và kiểm thử rõ `NaN`/`±0.0`; không tự suy diễn chỉ từ các biểu thức boolean `a < b`, `a > b`. Với chuỗi quốc tế, nếu dùng `Collator` thì thống nhất locale, quy tắc chuẩn hóa và cấu hình trong suốt quá trình so sánh.

## 7. Đưa bộ kiểm chứng vào unit test

Hàm `checkContract` ở ví dụ có thể đưa vào tiện ích test và gọi trong test case bằng một tập mẫu cố định. Khi dùng JUnit, chỉ cần để `AssertionError` lan ra; test runner sẽ báo FAIL. Nên có **ít nhất một bộ ba đã biết sẽ thất bại** cho mỗi loại comparator lỗi được sửa, nhằm tránh chỉ kiểm thử tình huống dễ.

Có thể kiểm tra thêm các thuộc tính ở mức dữ liệu thực:

- Kết quả so sánh lặp lại cùng cặp không đổi khi khóa chưa đổi.
- Sau khi sort, mọi cặp liên tiếp không giảm theo comparator; đồng thời kiểm tra bộ ba vì thứ tự đầu ra “trông đã sort” không chứng minh comparator hợp lệ.
- Nếu ứng dụng yêu cầu `compare(a,b)==0` tương đương `a.equals(b)`, kiểm tra **điều kiện nghiệp vụ bổ sung này** riêng biệt. Một comparator đúng hợp đồng thứ tự vẫn có thể cố ý không nhất quán với `equals()`.

Khi một bộ ba thất bại, sửa chính thuật toán so sánh: quy tắc so khóa, tie-breaker, xử lý `null`, tràn số, hoặc nguồn dữ liệu mutable. Thay đổi thứ tự duyệt mẫu để “test xanh” không giải quyết lỗi.

## 8. Checklist tự kiểm tra

- Nếu `compare(a,b)=42` thì có hợp lệ không? **Có**, miễn là dấu và tất cả điều kiện hợp đồng đúng; không cần là `1`.
- Nếu `a<b`, `b<c` nhưng `a>c`, vi phạm gì? **Bắc cầu**, cần bộ ba để phát hiện.
- Nếu `compare(a,b)==0`, có bắt buộc `a.equals(b)` không? **Không trong mọi trường hợp**, nhưng quan hệ so sánh của cả hai với `c` phải cùng dấu; `TreeSet`/`TreeMap` xem chúng là cùng khóa theo thứ tự.
- Tại sao dùng `Integer.signum`? Để kiểm chứng **dấu**, tránh giả định giá trị `±1` và tránh tràn khi đổi dấu số nguyên thô.
- Vì sao `PASS` với 5 phần tử chưa đủ kết luận comparator luôn đúng? Tất cả bộ ba chỉ được kiểm tra trong **tập 5 mẫu**; lỗi có thể xuất hiện tại giá trị biên hoặc lớp dữ liệu chưa xét.

**Ghi nhớ:** để tin cậy một `compareTo()` hay `Comparator`, hãy kiểm tra cả **cặp đảo chiều** và **mọi bộ ba đại diện**, đặc biệt những bộ ba chứa hai phần tử `compare == 0`. Kết quả sắp xếp nhìn hợp lý trên vài ví dụ là chưa đủ để chứng minh hợp đồng thứ tự.

## Tham khảo

- [Java SE 17 — Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
