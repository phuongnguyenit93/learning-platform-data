# Comparator: tính bắc cầu và tính nhất quán với equals

**Chủ đề:** Java 8 → Comparator → Tính bắc cầu và tính nhất quán với equals.

Trong Java, **Comparator<T>** xác định thứ tự so sánh hai đối tượng bằng phương thức **compare(a, b)**. Thao tác tưởng như đơn giản này có tác động trực tiếp đến **List.sort()**, **Stream.sorted()**, **TreeSet**, **TreeMap**, **Arrays.sort()**, tìm kiếm nhị phân và nhiều cấu trúc dữ liệu có thứ tự.

Một comparator có thể hoạt động đúng khi thử với hai phần tử nhưng **sai khi xuất hiện phần tử thứ ba**. Đây là lý do cần quan tâm đến **tính bắc cầu (transitivity)**. Ngoài ra, hai đối tượng có thể được comparator coi là tương đương dù **equals()** trả false; điều đó đặc biệt ảnh hưởng đến cách **TreeSet/TreeMap xác định phần tử hoặc khóa đã có**.

API **Comparator** và những hợp đồng này vẫn áp dụng trong Java hiện hành. Các ví dụ độc lập dưới đây dùng **Java 17+**, với các tiện ích như **List.of(...)** và **record** chỉ nhằm làm mã ví dụ ngắn gọn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu **dấu** của **Comparator.compare(a, b)** thay vì nhầm rằng phương thức chỉ trả đúng -1, 0 hoặc 1.
2. Phát biểu và kiểm tra **tính phản xứng về dấu**, **tính bắc cầu**, và quy tắc **nhất quán của lớp so sánh bằng 0**.
3. Phân biệt **bắt buộc tuân thủ hợp đồng Comparator** với **khuyến nghị nhất quán với equals**.
4. Giải thích vì sao **TreeSet/TreeMap** có thể gộp hai object mà **HashSet/HashMap** coi là khác.
5. Nhận diện tình huống kinh điển: **BigDecimal("2.0")** và **BigDecimal("2.00")**, so sánh chuỗi **không phân biệt hoa thường**, hay chỉ so sánh một trường.
6. Viết comparator an toàn bằng **comparing**, **comparingInt/Long/Double**, **thenComparing** và các phương thức **compare**.
7. Tránh tràn số do viết **a - b**, so sánh không bắc cầu, comparator có trạng thái biến đổi, dữ liệu nullable và lựa chọn khóa sắp xếp không phù hợp.
8. Viết test kiểm tra các luật comparator trên tập dữ liệu có giá trị biên.

## 2. Comparator<T> thực sự định nghĩa điều gì?

Giao diện cốt lõi là **java.util.Comparator<T>**. Phương thức quan trọng:

~~~java
int compare(T a, T b);
~~~

Đây là **chữ ký API minh họa**, không phải phương thức cần viết lại trong mọi class.

| Dấu của compare(a, b) | Ý nghĩa |
|---|---|
| **Âm** | a đứng **trước** b |
| **0** | a và b **tương đương theo comparator** |
| **Dương** | a đứng **sau** b |

**Chỉ xét dấu.** Một comparator hợp lệ có thể trả -7, 0 hoặc 42; không có quy định mọi comparator phải trả đúng -1 và 1 cho hai chiều. Do đó, kiểm tra **compare(a,b) < 0**, **== 0**, **> 0** hoặc dùng **Integer.signum(...)** khi cần kiểm tra tính chất.

Ví dụ comparator theo số nguyên:

~~~java
Comparator<Integer> order = Integer::compare;

int result = order.compare(3, 10);
// result < 0 là true
~~~

Đoạn minh họa cần import **java.util.Comparator**. **Integer.compare(...)** biểu diễn thứ tự số nguyên mà không cần trừ trực tiếp.

**Quan trọng:** **compare(a,b) == 0** là **tương đương theo tiêu chí sắp xếp**. Nó không nhất thiết khẳng định **a.equals(b)** nếu comparator được thiết kế theo một tiêu chí hẹp hơn.

### 2.1. Quan hệ thứ tự và lớp tương đương

Một comparator xác định các lớp phần tử được coi là ngang hàng khi so sánh:

~~~text
compare(a,b) < 0:  a đứng trước b
compare(a,b) = 0:  a và b thuộc cùng lớp tương đương so sánh
compare(a,b) > 0:  a đứng sau b
~~~

Ví dụ comparator chỉ dựa trên **độ dài chuỗi**:

~~~text
"a"          → độ dài 1
"ab", "xy"   → cùng độ dài 2
"hello"      → độ dài 5
~~~

Theo comparator dựa vào độ dài, **"ab"** và **"xy"** tương đương, dù **"ab".equals("xy")** là false. Comparator như vậy **có thể hợp lệ về thứ tự** nếu nó vẫn tuân thủ các luật so sánh, nhưng **không nhất quán với equals**.

## 3. Ba điều kiện bắt buộc của hợp đồng Comparator

Với mọi đối tượng x, y, z mà comparator hỗ trợ so sánh, đặc tả Java yêu cầu các quy tắc sau. Đây **không phải** những gợi ý có thể bỏ qua nếu muốn dùng comparator trong phép sắp xếp hoặc tập hợp có thứ tự.

### 3.1. Phản xứng về dấu (sign symmetry)

Quy tắc:

~~~text
sgn(compare(x, y)) == -sgn(compare(y, x))
~~~

Trong đó **sgn** biến một số nguyên âm thành -1, số 0 thành 0 và số nguyên dương thành 1.

Ví dụ với thứ tự số tự nhiên:

~~~text
compare(1, 2) < 0
compare(2, 1) > 0
compare(5, 5) == 0
~~~

Nếu x đứng trước y thì y phải đứng sau x. Nếu compare(x,y)==0, chiều ngược lại cũng phải bằng 0.

Đặc tả còn yêu cầu: nếu **compare(x,y)** ném một ngoại lệ thì **compare(y,x)** cũng phải ném ngoại lệ (trong cùng miền đầu vào đó). **null** có thể không được hỗ trợ, tùy comparator; quy tắc không buộc mọi comparator phải chấp nhận null.

**Lỗi thường gặp:** so sánh bằng phép trừ có thể làm hai chiều cùng âm do tràn số nguyên, vi phạm phản xứng.

### 3.2. Tính bắc cầu (transitivity)

Theo đặc tả:

~~~text
compare(x, y) > 0 và compare(y, z) > 0
    ⇒ compare(x, z) > 0
~~~

Tương đương với hướng nhỏ hơn:

~~~text
x < y và y < z
    ⇒ x < z
~~~

Nếu thứ tự nói **A trước B**, **B trước C** nhưng **C trước A**, không thể xếp một cách nhất quán. Một thuật toán sort không thể tạo thứ tự toàn cục thỏa mãn các khẳng định mâu thuẫn đó.

Ví dụ đúng:

~~~text
10 < 20
20 < 30
⇒ 10 < 30
~~~

Ví dụ sai dạng vòng tròn:

~~~text
0 < 1
1 < 2
2 < 0
~~~

Ba khẳng định này tự mâu thuẫn về quan hệ thứ tự. Dù so sánh từng cặp có vẻ hợp lý theo một quy tắc "thắng-thua", nó không phải comparator thích hợp cho **sort**, **TreeSet** hoặc **TreeMap**.

**Tính bắc cầu không phải yêu cầu chỉ dành cho parallel stream hoặc dữ liệu lớn.** Bất cứ comparator dùng với thuật toán sắp xếp thông thường nào cũng cần tuân thủ.

### 3.3. Nhất quán với lớp so sánh bằng 0 (zero-equivalence consistency)

Đặc tả Comparator còn có một điều kiện quan trọng:

~~~text
compare(x, y) == 0
    ⇒ sgn(compare(x, z)) == sgn(compare(y, z))
       với mọi z
~~~

Nghĩa là: nếu comparator coi **x** và **y** ngang hàng, thì khi so với một đối tượng **z** bất kỳ, hai đối tượng đó phải có **cùng hướng so sánh**.

Ví dụ comparator theo độ dài chuỗi:

~~~text
x = "ab", y = "xy"  → cùng độ dài, compare(x,y)==0
z = "hello"         → dài hơn cả x và y

compare(x,z)<0 và compare(y,z)<0
~~~

Điều này hợp lệ. Ngược lại, nếu x và y được coi ngang hàng nhưng x đứng trước z còn y đứng sau z, các nhóm tương đương không còn có một vị trí nhất quán trong thứ tự.

**Đừng bỏ qua quy tắc này chỉ vì đã kiểm tra tính bắc cầu trong vài tình huống.** Khi tự định nghĩa logic so sánh có nhiều nhánh đặc biệt, cần kiểm tra cả những cặp mà comparator trả 0.

### 3.4. Ba luật và một khuyến nghị — bảng phân biệt

| Quy tắc | Điều kiện | Bắt buộc? |
|---|---|---|
| Phản xứng về dấu | **sgn(c(x,y)) == -sgn(c(y,x))** | **Có** |
| Bắc cầu | **c(x,y)>0 và c(y,z)>0 ⇒ c(x,z)>0** | **Có** |
| Nhất quán với lớp bằng 0 | **c(x,y)==0 ⇒ sgn(c(x,z))==sgn(c(y,z))** | **Có** |
| Nhất quán với equals | **c(x,y)==0 ⇔ x.equals(y)** | **Thường nên có, nhưng không bắt buộc tuyệt đối** |

Trong bảng, **c** là cách viết tắt của **Comparator.compare**.

**Lưu ý đặc biệt:** "Nhất quán với lớp bằng 0" là **một điều kiện bắt buộc của Comparator**; nó **khác** với "nhất quán với Object.equals". Hai khái niệm thường bị gộp nhầm thành một.

## 4. Tính nhất quán với equals là gì?

Một comparator được coi là **consistent with equals** nếu, với mọi x và y thuộc miền hỗ trợ:

~~~text
compare(x, y) == 0  ⇔  x.equals(y)
~~~

Ký hiệu **⇔** có nghĩa là **hai chiều**:

1. Nếu comparator trả 0 thì **equals** phải true.
2. Nếu **equals** true thì comparator phải trả 0.

Như vậy, quan hệ "bằng nhau theo thứ tự" và quan hệ "bằng nhau theo Object.equals" chia dữ liệu thành **cùng các nhóm tương đương**.

### 4.1. Có bắt buộc comparator luôn consistent with equals không?

**Không phải trong mọi trường hợp.** API Comparator khuyến nghị điều đó, nhưng chấp nhận comparator hợp lệ về thứ tự mà không nhất quán với equals, miễn nó tuân thủ **ba quy tắc bắt buộc** ở trên.

Ví dụ:

~~~java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
~~~

Đây là đoạn minh họa; cần import **java.util.Comparator**. Comparator hợp lệ để **sắp xếp chuỗi theo độ dài**, nhưng coi **"ab"** và **"xy"** là ngang nhau vì đều dài 2, trong khi **String.equals** nói chúng khác nhau.

Khi **chỉ muốn sắp List theo độ dài**, điều đó có thể là một chủ ý hoàn toàn hợp lệ. Khi **dùng comparator để quyết định phần tử duy nhất của TreeSet hoặc khóa của TreeMap**, hệ quả có thể khác mong đợi.

### 4.2. Khi nào việc không nhất quán với equals gây vấn đề?

**TreeSet** và **TreeMap** so sánh phần tử/khóa bằng **compare** (hoặc **compareTo** của natural ordering) để quyết định vị trí và tính tương đương. Hai phần tử có **compare(x,y)==0** được chúng coi là cùng một "slot" thứ tự.

- Với **TreeSet**, thêm phần tử thứ hai tương đương theo comparator có thể **không tăng size**, ngay cả khi **equals** nói hai đối tượng khác nhau.
- Với **TreeMap**, đặt một value dưới khóa tương đương theo comparator có thể **thay value** của mapping đang có, dù hai object key không equals.
- **HashSet/HashMap** về cơ bản sử dụng **equals/hashCode** để xác định phần tử/khóa tương đương, nên có thể giữ cả hai object mà TreeSet/TreeMap gộp vào một vị trí.

Vì **Set/Map** có hợp đồng về bình đẳng dựa trên **equals**, một sorted set/map dùng ordering không nhất quán với equals có thể không tuân thủ đầy đủ hợp đồng tổng quát của Set/Map khi so sánh với các implementation khác. Thứ tự của TreeSet/TreeMap vẫn được triển khai theo comparator; đây **không phải lỗi Java**, mà là lựa chọn ngữ nghĩa cần hiểu trước khi sử dụng.

Nếu chủ ý chỉ cần **mỗi nhóm độ dài một đại diện**, comparator theo độ dài có thể phù hợp với cấu trúc tập theo nhóm. Nhưng phải viết rõ quy tắc đó và không giả định Set này hoạt động như HashSet về nhận diện phần tử.

## 5. Ví dụ hoàn chỉnh: compare==0 khác equals trong TreeSet

Lưu thành **ComparatorEqualityDemo.java**:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorEqualityDemo {
    public static void main(String[] args) {
        String a = "ab";
        String b = "xy";

        Comparator<String> byLength =
                Comparator.comparingInt(String::length);

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareZero="
                + (byLength.compare(a, b) == 0));

        Set<String> hash = new HashSet<>(List.of(a, b));
        Set<String> tree = new TreeSet<>(byLength);
        tree.addAll(List.of(a, b));

        System.out.println("hashSize=" + hash.size());
        System.out.println("treeSize=" + tree.size());
        System.out.println("treeContainsXY="
                + tree.contains("xy"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorEqualityDemo.java
java ComparatorEqualityDemo
~~~

**Stdout:**

~~~text
equals=false
compareZero=true
hashSize=2
treeSize=1
treeContainsXY=true
~~~

**Diễn giải:**

- Hai chuỗi khác nhau nên **a.equals(b)==false**.
- Độ dài giống nhau nên **byLength.compare(a,b)==0**.
- **HashSet** giữ hai phần tử vì xét equals/hashCode.
- **TreeSet** chỉ có một phần tử theo comparator độ dài.
- **tree.contains("xy")==true** không chứng minh chính object **"xy"** đã được lưu trong tập; phương thức dùng tiêu chí tương đương của TreeSet.

**Không dựa vào thứ tự in HashSet** khi kiểm thử: HashSet không cam kết encounter order. Ví dụ chỉ in kích thước và kết quả contains để giữ stdout ổn định.

**Bài học:** trước khi dùng comparator cho một sorted set/map, hãy hỏi **"compare==0 có đúng nghĩa là hai phần tử cần được coi là cùng một không?"**.

## 6. Lỗi lớn: dùng phép trừ để so sánh int

Một anti-pattern phổ biến:

~~~java
// KHÔNG an toàn cho toàn miền int:
Comparator<Integer> bad = (a, b) -> a - b;
~~~

Đoạn này có thể cho kết quả đúng với số nhỏ, nhưng **a-b được tính bằng int** và có thể tràn. Khi kết quả tràn đổi dấu, comparator vi phạm thứ tự số học; trong trường hợp đặc biệt, hai chiều đều có dấu âm, **vi phạm phản xứng**.

Ví dụ:

~~~text
a = Integer.MIN_VALUE = -2147483648
b = 0

a - b = -2147483648  (âm)
b - a = -2147483648  (tràn int, cũng âm)

Comparator nói a < b và đồng thời b < a.
~~~

Một comparator dựa trên tràn số như vậy có thể cho kết quả sort sai, hành vi khó đoán khi tìm kiếm hoặc xây dựng tập có thứ tự. Không dựa vào việc sort tự phát hiện mọi vi phạm.

**Cách đúng:**

~~~java
Comparator<Integer> good = Integer::compare;
// Hoặc: Comparator.comparingInt(Integer::intValue)
~~~

Với **long**, dùng **Long.compare(a,b)** thay vì **(int)(a-b)** hoặc phép trừ long có nguy cơ tràn. Với **double**, dùng **Double.compare(a,b)** thay vì phép trừ/cast hoặc tự xét dấu bằng so sánh không xử lý NaN đúng.

### 6.1. Ví dụ hoàn chỉnh: tràn số làm mất phản xứng

Lưu thành **ComparatorOverflowDemo.java**:

~~~java
import java.util.Comparator;

public class ComparatorOverflowDemo {
    public static void main(String[] args) {
        Comparator<Integer> bad = (a, b) -> a - b;
        Comparator<Integer> good = Integer::compare;

        int min = Integer.MIN_VALUE;
        int zero = 0;

        System.out.println("badForward="
                + Integer.signum(bad.compare(min, zero)));
        System.out.println("badReverse="
                + Integer.signum(bad.compare(zero, min)));

        System.out.println("goodForward="
                + Integer.signum(good.compare(min, zero)));
        System.out.println("goodReverse="
                + Integer.signum(good.compare(zero, min)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorOverflowDemo.java
java ComparatorOverflowDemo
~~~

**Stdout:**

~~~text
badForward=-1
badReverse=-1
goodForward=-1
goodReverse=1
~~~

Ở hai dòng đầu, comparator sai nói **min trước 0** và **0 trước min**. Dùng **Integer.compare** giữ được dấu đúng.

**Đừng chỉ sửa bằng Math.abs(a-b):** **Math.abs(Integer.MIN_VALUE)** vẫn là giá trị âm vì không có số dương int biểu diễn được độ lớn đó. Hãy so sánh trực tiếp qua phương thức **compare**, không tạo khoảng cách bằng phép trừ không kiểm tra.

## 7. Ví dụ mất tính bắc cầu: thứ tự vòng tròn

Giả sử có ba trạng thái **0, 1, 2** và ta viết một "thứ tự" kiểu vòng tròn:

~~~text
0 đứng trước 1
1 đứng trước 2
2 đứng trước 0
~~~

Quan hệ này có thể phù hợp với trò chơi "đánh bại nhau" hoặc lịch luân phiên, nhưng **không phải thứ tự có tính bắc cầu** để sắp xếp một danh sách.

Đoạn mã thể hiện ý tưởng (miền giá trị chỉ gồm 0,1,2):

~~~java
Comparator<Integer> cyclic = (a, b) ->
        a.equals(b) ? 0
                : ((a + 1) % 3 == b ? -1 : 1);
~~~

**Lỗi logic:** hàm nói **0<1** và **1<2**, nhưng đồng thời nói **0>2**. Những khẳng định mâu thuẫn này không thể được giải quyết chỉ bằng cách "chạy sort một lần nữa".

### 7.1. Có phải Arrays.sort/List.sort luôn ném lỗi nếu comparator sai?

**Không.** Các thuật toán sắp xếp trong JDK có thể phát hiện và ném **IllegalArgumentException** khi thấy comparator vi phạm hợp đồng, nhưng **không được bảo đảm mọi comparator sai đều bị phát hiện**. Với đầu vào nhỏ, code có thể vẫn chạy mà không báo lỗi nhưng cho thứ tự không có ý nghĩa toàn cục.

**Không viết unit test kỳ vọng một comparator sai nhất định phải ném exception khi sort**. Thay vào đó, kiểm thử **các luật comparator** và sửa logic so sánh.

## 8. Kiểm thử các luật bằng bộ kiểm tra ba phần tử

Có thể xây một phép kiểm thử chạy qua mọi cặp/ba phần tử của một tập mẫu nhỏ, để phát hiện những sai phạm thông thường. Phương pháp này **không chứng minh đúng cho mọi dữ liệu trong toàn miền**, nhưng đặc biệt hiệu quả khi đưa vào các giá trị biên như **Integer.MIN_VALUE**, **0**, **Integer.MAX_VALUE**, chuỗi cùng độ dài, trường hợp null hoặc các nhóm so sánh bằng 0.

Lưu thành **ComparatorContractTestDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;

public class ComparatorContractTestDemo {
    static <T> void checkRequiredLaws(
            List<T> values,
            Comparator<? super T> comparator) {

        for (T x : values) {
            for (T y : values) {
                int xy = Integer.signum(
                        comparator.compare(x, y));
                int yx = Integer.signum(
                        comparator.compare(y, x));

                if (xy != -yx) {
                    throw new IllegalArgumentException(
                            "antisymmetry");
                }

                for (T z : values) {
                    int yz = Integer.signum(
                            comparator.compare(y, z));
                    int xz = Integer.signum(
                            comparator.compare(x, z));

                    if (xy > 0 && yz > 0 && xz <= 0) {
                        throw new IllegalArgumentException(
                                "transitivity");
                    }

                    if (xy == 0 && xz != yz) {
                        throw new IllegalArgumentException(
                                "zeroConsistency");
                    }
                }
            }
        }
    }

    static <T> String verdict(
            List<T> values,
            Comparator<? super T> comparator) {
        try {
            checkRequiredLaws(values, comparator);
            return "PASS";
        } catch (IllegalArgumentException ex) {
            return "FAIL_" + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        Comparator<Integer> natural = Integer::compare;
        Comparator<Integer> subtraction = (a, b) -> a - b;

        Comparator<Integer> cyclic = (a, b) ->
                a.equals(b) ? 0
                        : ((a + 1) % 3 == b ? -1 : 1);

        List<Integer> boundaries = List.of(
                Integer.MIN_VALUE,
                0,
                Integer.MAX_VALUE
        );

        System.out.println("natural="
                + verdict(boundaries, natural));

        System.out.println("subtraction="
                + verdict(boundaries, subtraction));

        System.out.println("cycle="
                + verdict(List.of(0, 1, 2), cyclic));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorContractTestDemo.java
java ComparatorContractTestDemo
~~~

**Stdout:**

~~~text
natural=PASS
subtraction=FAIL_antisymmetry
cycle=FAIL_transitivity
~~~

**Giải thích cấu trúc test:**

- Vòng lặp hai lớp x/y kiểm tra **phản xứng về dấu**.
- Vòng lặp ba lớp x/y/z kiểm tra điều kiện **x>y và y>z ⇒ x>z**.
- Khi **xy==0**, test kiểm tra **dấu so sánh với z** có bằng nhau không.
- **natural** với Integer.compare tuân thủ luật trên tập biên.
- **subtraction** thất bại vì **tràn int** khiến so sánh hai chiều có cùng dấu.
- **cyclic** thất bại vì so sánh vòng tròn **không bắc cầu**.

**Giới hạn của phép test:**

1. Chỉ kiểm tra các giá trị trong **values**. Với miền dữ liệu vô hạn, nên bổ sung randomized/property-based testing và ví dụ biên.
2. Chi phí thử các bộ ba là **O(n³)**, phù hợp với tập mẫu nhỏ, không dùng trên hàng triệu phần tử.
3. Bộ kiểm tra này xét **ba luật bắt buộc**, **chưa kiểm tra tính nhất quán với equals**, vì đặc tả Comparator cho phép không nhất quán với equals khi có chủ ý.
4. Nếu comparator hỗ trợ null, tập test có thể dùng list cho phép null. Nếu comparator không hỗ trợ null, không đưa null vào miền hợp lệ cần kiểm tra.
5. Một comparator có trạng thái phụ thuộc thời gian hoặc tự biến đổi có thể cho kết quả thay đổi giữa các lần gọi. Hãy coi đó là dấu hiệu thiết kế sai; kiểm tra lặp lại có thể phát hiện nhưng không chứng minh tính ổn định.

### 8.1. Bổ sung test nhất quán với equals khi nghiệp vụ cần

Khi comparator được dùng làm thứ tự cho **TreeSet/TreeMap** và ứng dụng yêu cầu nhận diện đối tượng theo **Object.equals**, có thể kiểm tra thêm:

~~~java
// Đoạn minh họa; giả sử x, y không null
// và comparator có kiểu Comparator<T>.
boolean sameByOrder = comparator.compare(x, y) == 0;
boolean sameByEquals = x.equals(y);

if (sameByOrder != sameByEquals) {
    throw new AssertionError("inconsistent with equals");
}
~~~

**Không gộp test này thành luật bắt buộc cho mọi comparator.** Ví dụ comparator theo độ dài chuỗi có thể cố ý đặt nhiều chuỗi khác nhau vào cùng nhóm; khi dùng chỉ để sort, đó là quyết định hợp lệ. Mục tiêu test phụ thuộc hợp đồng nghiệp vụ.

## 9. Cách xây comparator bắc cầu bằng composition

Với dữ liệu nghiệp vụ, cách an toàn và dễ đọc thường là **so sánh theo các khóa được xác định rõ ràng**:

1. So sánh khóa chính.
2. Nếu khóa chính bằng nhau (compare==0), so sánh khóa phụ.
3. Tiếp tục thêm khóa nếu cần.
4. Chỉ trả 0 khi các khóa quyết định sự tương đương đã bằng nhau.

Java có các factory và default method:

| API | Tác dụng |
|---|---|
| **Comparator.comparing(keyExtractor)** | So sánh theo một khóa có thứ tự tự nhiên |
| **Comparator.comparing(keyExtractor, keyComparator)** | So sánh theo một khóa với Comparator được chỉ rõ |
| **Comparator.comparingInt/Long/Double** | So sánh theo khóa kiểu primitive mà không cần phép trừ thủ công |
| **thenComparing(...)** | Thêm khóa phụ khi các khóa trước cho kết quả 0 |
| **thenComparingInt/Long/Double** | Thêm khóa phụ kiểu primitive |
| **reversed()** | Đảo chiều một comparator hợp lệ |
| **naturalOrder()/reverseOrder()** | Thứ tự tự nhiên và đảo chiều của kiểu Comparable |
| **nullsFirst()/nullsLast()** | Định nghĩa cách đặt giá trị null trước hoặc sau giá trị khác null |

**Lưu ý:** các helper giúp xây quy tắc rõ ràng, nhưng **không tự làm một keyExtractor có tác dụng phụ hoặc một comparator tùy biến sai trở nên hợp lệ**. Ví dụ **thenComparing** với một comparator vi phạm bắc cầu vẫn có thể tạo kết quả sai.

### 9.1. thenComparing tạo thứ tự từ điển (lexicographic)

Giả sử kiểu record:

~~~java
record Person(String name, int age) {}
~~~

Theo Java 17+, **record** tự có **equals/hashCode** dựa trên các component. Comparator sau so sánh theo tuổi rồi tên:

~~~java
Comparator<Person> byAgeThenName =
        Comparator.comparingInt(Person::age)
                .thenComparing(Person::name);
~~~

Với **name khác null** và dữ liệu Person hợp lệ, comparator có ba tính chất tốt:

- Tuân thủ thứ tự số nguyên cho age và thứ tự từ điển cho String name.
- Dùng tên làm tie-breaker khi hai người cùng tuổi.
- **compare(a,b)==0** khi và chỉ khi **age và name cùng bằng nhau**, trùng với **record Person.equals** trong ví dụ này.

**Không phát biểu rằng "thenComparing luôn làm comparator consistent with equals".** Điều đó chỉ đúng nếu **các khóa đang xét đủ để phân biệt mọi component mà equals dùng** và cách so sánh khóa cũng nhất quán với equals.

Ví dụ nếu thêm component **employeeId** vào record nhưng comparator chỉ xét **name và age**, hai object có id khác nhau có thể compare==0 dù record.equals false. Cần thêm **thenComparing(Person::employeeId)** hoặc định nghĩa một mô hình equals/order phù hợp.

### 9.2. Chương trình hoàn chỉnh: comparator cho record

Lưu thành **ComparatorCompositionDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorCompositionDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        List<Person> people = List.of(
                new Person("Binh", 25),
                new Person("An", 30),
                new Person("An", 25)
        );

        Comparator<Person> byAgeThenName =
                Comparator.comparingInt(Person::age)
                        .thenComparing(Person::name);

        List<Person> sorted = people.stream()
                .sorted(byAgeThenName)
                .toList();

        System.out.println("sorted=" + sorted);

        Person x = new Person("An", 25);
        Person y = new Person("An", 25);
        Person z = new Person("An", 30);

        System.out.println("equalsSame=" + x.equals(y));
        System.out.println("compareSame="
                + (byAgeThenName.compare(x, y) == 0));
        System.out.println("differentAge="
                + (byAgeThenName.compare(x, z) != 0));

        TreeSet<Person> set = new TreeSet<>(byAgeThenName);
        set.addAll(people);
        System.out.println("setSize=" + set.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorCompositionDemo.java
java ComparatorCompositionDemo
~~~

**Stdout:**

~~~text
sorted=[Person[name=An, age=25], Person[name=Binh, age=25], Person[name=An, age=30]]
equalsSame=true
compareSame=true
differentAge=true
setSize=3
~~~

**Giải thích:** comparator sắp tuổi tăng dần, tên là khóa phụ. Nó không viết **a.age()-b.age()** nên tránh overflow; với kiểu Person chỉ có **name và age**, comparator zero khớp record.equals (giả sử name không null).

**Stream.sorted(comparator)** trả pipeline có thứ tự sắp; nó không làm thay đổi **people** ban đầu. **TreeSet** dùng comparator để giữ một phần tử cho mỗi lớp tương đương. Ở ví dụ này, ba record khác nhau nên kích thước là 3.

## 10. Trường hợp kinh điển: BigDecimal.compareTo không giống equals

**BigDecimal** biểu diễn số thập phân bằng **giá trị số và scale**. Hai đối tượng có thể mang cùng giá trị toán học nhưng scale khác nhau:

~~~java
BigDecimal a = new BigDecimal("2.0");  // scale = 1
BigDecimal b = new BigDecimal("2.00"); // scale = 2
~~~

- **a.compareTo(b) == 0** vì cả hai có giá trị số học bằng 2.
- **a.equals(b) == false** vì **equals** còn xét scale.
- **a.hashCode()** và **b.hashCode()** có thể khác theo quy tắc biểu diễn.

Vì thế **natural ordering của BigDecimal không nhất quán với equals**. Đây là hành vi được tài liệu BigDecimal ghi rõ, không phải bug.

### 10.1. Hệ quả với HashSet và TreeSet

Lưu thành **BigDecimalComparatorDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalComparatorDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareZero=" + (a.compareTo(b) == 0));

        HashSet<BigDecimal> hash =
                new HashSet<>(List.of(a, b));

        TreeSet<BigDecimal> natural =
                new TreeSet<>(List.of(a, b));

        System.out.println("hashSize=" + hash.size());
        System.out.println("treeSize=" + natural.size());

        Comparator<BigDecimal> withScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);

        TreeSet<BigDecimal> precise = new TreeSet<>(withScale);
        precise.addAll(List.of(a, b));

        System.out.println("scaleAwareSize=" + precise.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BigDecimalComparatorDemo.java
java BigDecimalComparatorDemo
~~~

**Stdout:**

~~~text
equals=false
compareZero=true
hashSize=2
treeSize=1
scaleAwareSize=2
~~~

**Diễn giải:**

- **HashSet** dùng equals/hashCode: hai BigDecimal khác scale được giữ riêng.
- **TreeSet** dùng natural ordering: compareTo trả 0, nên chỉ còn một phần tử theo comparator.
- Comparator **naturalOrder().thenComparingInt(BigDecimal::scale)** ưu tiên giá trị số học, rồi dùng **scale để phân biệt** những cách biểu diễn khác nhau cùng một giá trị. Với BigDecimal, nếu giá trị số và scale đều giống nhau thì unscaled value cũng giống nhau, do đó quan hệ zero của comparator này trùng với BigDecimal.equals.

**Chọn semantics trước khi chọn comparator:**

- Nếu nghiệp vụ muốn **2.0 và 2.00 coi như cùng số tiền/đại lượng**, việc gộp theo compareTo có thể là chủ ý. Nhưng phải biết SortedSet/SortedMap không có cùng tiêu chí nhận diện với HashSet/HashMap.
- Nếu nghiệp vụ cần **giữ riêng biểu diễn theo scale**, hãy dùng comparator phù hợp với equals như ví dụ **withScale**, hoặc thống nhất dạng dữ liệu ở ranh giới nhập liệu.
- Không dùng **new BigDecimal(double)** chỉ để "sửa" vấn đề: cách đó còn có thể mang sai số chuyển từ double. Để biểu diễn số thập phân đã biết, ví dụ dùng **new BigDecimal("2.00")**.

## 11. So sánh chuỗi không phân biệt hoa thường

**String.CASE_INSENSITIVE_ORDER** là một Comparator so sánh chuỗi không phân biệt hoa/thường; nó có thể là thứ tự **hợp lệ và bắc cầu** nhưng không nhất quán với **String.equals**, vốn phân biệt hoa/thường.

Ví dụ:

~~~text
"Java".equals("java")                         → false
String.CASE_INSENSITIVE_ORDER.compare(...)     → 0
~~~

Nếu chỉ muốn sắp danh sách mà những chuỗi chỉ khác chữ hoa/chữ thường đứng gần nhau, cách so sánh đó có thể phù hợp. Nếu dùng cho **TreeSet/TreeMap**, chúng sẽ được coi là **tương đương theo comparator**.

### 11.1. Ví dụ hoàn chỉnh với TreeSet và TreeMap

Lưu thành **CaseInsensitiveComparatorDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;

public class CaseInsensitiveComparatorDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "java", "Go");

        TreeSet<String> ignoreCase =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCase.addAll(words);

        System.out.println("ignoreCase=" + ignoreCase);

        Comparator<String> strict =
                String.CASE_INSENSITIVE_ORDER
                        .thenComparing(Comparator.naturalOrder());

        TreeSet<String> strictSet = new TreeSet<>(strict);
        strictSet.addAll(words);
        System.out.println("strictSet=" + strictSet);

        TreeMap<String, Integer> map =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        map.put("Java", 1);
        map.put("java", 2);

        System.out.println("treeMap=" + map);
        System.out.println("lookup=" + map.get("JAVA"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaseInsensitiveComparatorDemo.java
java CaseInsensitiveComparatorDemo
~~~

**Stdout:**

~~~text
ignoreCase=[Go, Java]
strictSet=[Go, Java, java]
treeMap={Java=2}
lookup=2
~~~

**Giải thích:**

1. Với **CASE_INSENSITIVE_ORDER**, **"Java"** và **"java"** so sánh bằng 0, nên TreeSet chỉ giữ một đại diện cho hai chuỗi.
2. Comparator **strict** lấy thứ tự không phân biệt hoa thường làm khóa chính, nhưng khi ngang nhau dùng **naturalOrder** phân biệt đúng từng ký tự làm tie-breaker. Hai String khác nhau không còn bị gộp chỉ do khác hoa/thường; comparator zero tương ứng với **String.equals**.
3. **TreeMap** coi **"Java"** và **"java"** là một khóa logic theo comparator. Lần put thứ hai cập nhật value thành 2; tra bằng **"JAVA"** cũng tìm thấy mapping đó.
4. Không suy ra rằng **String.equals** đã thay đổi: nó vẫn phân biệt hai chuỗi. Chỉ **ngữ nghĩa so sánh của TreeSet/TreeMap** thay đổi.

**Lưu ý quốc tế hóa:** so sánh không phân biệt hoa thường trong Java không phải mọi quy tắc sắp xếp ngôn ngữ tự nhiên. Nếu cần thứ tự từ điển theo locale, hãy cân nhắc **Collator** với cấu hình và quy tắc nghiệp vụ phù hợp; đừng đánh đồng việc fold chữ với thứ tự văn hóa. Comparator cũng phải được ổn định trong suốt thời gian dùng để làm khóa của sorted collection.

## 12. So sánh một trường không đủ nhận diện object

Giả sử có:

~~~java
record Employee(String id, String name, int age) {}
~~~

Với record này, **equals** xét **id, name và age**. Comparator chỉ dựa trên tuổi:

~~~java
Comparator<Employee> onlyAge =
        Comparator.comparingInt(Employee::age);
~~~

Hai Employee khác id/name nhưng cùng age sẽ có **compare==0**. Việc ấy có thể hợp lệ khi **chỉ sort danh sách theo tuổi**, nhưng trong **TreeSet<Employee>**, những Employee cùng tuổi bị coi là một nhóm và có thể chỉ còn một đại diện.

Nếu nghiệp vụ yêu cầu comparator zero iff record.equals, cần so sánh đủ những trường mà equals coi là thành phần định danh:

~~~java
Comparator<Employee> byAllFields =
        Comparator.comparingInt(Employee::age)
                .thenComparing(Employee::id)
                .thenComparing(Employee::name);
~~~

Đây là **đoạn minh họa**, cần **id** và **name** khác null, và giả định không có chính sách equality tùy biến. Nếu record có thêm một component khác, phải xem lại comparator.

**Không phải cứ thêm một ID vào cuối là luôn consistent with equals.** Nếu equals của class chỉ dùng ID còn comparator dùng age trước, hai object cùng ID nhưng age khác nhau có equals true mà comparator nonzero. Ngược lại, nếu equals dùng tất cả component, comparator chỉ dùng ID không đủ. Hãy thiết kế **equals và comparator cùng một chủ đích**.

### 12.1. Comparator theo khóa nghiệp vụ thay vì equals có phải sai?

Không nhất thiết. Có ứng dụng dùng cùng một **business key** để cố ý coi nhiều biểu diễn khác nhau là một mục. Khi đó nên:

- Nêu rõ **quy tắc "trùng" của sorted collection** là gì.
- Không giả định kích thước hoặc contains của TreeSet giống HashSet.
- Tránh so sánh trực tiếp hoặc hoán đổi dữ liệu giữa các Set/Map có quy tắc equality khác nhau mà chưa chuyển đổi/chuẩn hóa.
- Viết test minh họa trường hợp hai object **compare==0 nhưng equals false** để người bảo trì không ngạc nhiên.

## 13. Comparator trong List.sort, Stream.sorted và tìm kiếm

### 13.1. List.sort / Collections.sort

~~~java
List<Integer> values = new ArrayList<>(
        List.of(30, 10, 20)
);

values.sort(Integer::compare);
// values == [10, 20, 30]
~~~

Đây là đoạn minh họa, cần import **List** và **ArrayList**. **List.sort** thay thứ tự ngay trên List nếu List hỗ trợ sửa. **Collections.sort** vẫn là API hợp lệ, nhưng **List.sort** biểu đạt ý định trực tiếp khi đã có List.

Nếu Comparator không tuân thủ hợp đồng, kết quả có thể không đúng thứ tự mong muốn hoặc thuật toán có thể ném exception trong một số trường hợp; **không có lời bảo đảm mọi lỗi comparator đều được phát hiện**.

### 13.2. Stream.sorted

~~~java
List<Integer> original = List.of(30, 10, 20);

List<Integer> sorted = original.stream()
        .sorted(Integer::compare)
        .toList();

// original == [30, 10, 20]
// sorted == [10, 20, 30]
~~~

**Stream.sorted** tạo kết quả có thứ tự nhưng không sửa nguồn khi pipeline không có side effect. Với stream ordered, phép sort là **stable**: nếu comparator trả 0 cho hai phần tử, thứ tự tương đối của chúng được bảo toàn trong kết quả. Với stream unordered, không có bảo đảm stable tương ứng.

**Stable sort không sửa tính không nhất quán với equals**. Một comparator so sánh theo độ dài vẫn đặt các chuỗi cùng độ dài vào cùng lớp, nhưng **List** có thể giữ cả hai phần tử (không loại trùng). Trong **TreeSet**, chúng có thể bị gộp theo compare==0.

### 13.3. Collections.binarySearch

Khi tìm kiếm nhị phân trên List sorted theo comparator, phải dùng **cùng quy tắc comparator** cho việc tìm kiếm, vì thuật toán dựa trên thứ tự đó. Nếu comparator coi nhiều phần tử là ngang hàng, **binarySearch** có thể trả vị trí của một phần tử tương đương theo comparator, không nhất thiết object **equals** với khóa truy vấn.

**Không sort bằng so sánh case-insensitive rồi tìm bằng natural order.** Đó là hai quan hệ khác nhau, không thỏa tiền điều kiện của binary search.

### 13.4. SortedSet và SortedMap

**TreeSet, TreeMap** dùng comparator không chỉ để hiển thị thứ tự mà còn để **quản lý vị trí và tương đương khóa**. Khi comparator bị thay đổi về hành vi sau khi collection đã có dữ liệu (ví dụ đọc giá trị từ một biến mutable toàn cục), cấu trúc có thể không còn nhất quán với thứ tự nội bộ đã xây dựng.

**Không sửa thuộc tính dùng làm khóa so sánh của phần tử đang nằm trong TreeSet/TreeMap** khi việc sửa khiến thứ tự phải thay đổi. Muốn thay khóa, cách tiếp cận thường an toàn hơn là xóa mục cũ rồi thêm mục mới theo thứ tự mới, trong phạm vi đồng bộ/phân quyền cập nhật phù hợp.

## 14. Những loại dữ liệu cần đặc biệt cẩn thận

### 14.1. Số nguyên lớn và overflow

~~~java
// Rủi ro:
Comparator<Long> wrong = (a, b) -> (int) (a - b);

// Đúng:
Comparator<Long> correct = Long::compare;
~~~

Ép khoảng cách long về int có thể mất thông tin; phép trừ long còn có thể tràn. **Long.compare** so sánh trực tiếp toàn miền giá trị.

### 14.2. double, NaN, Infinity và -0.0

Không viết comparator double kiểu:

~~~java
// Không an toàn khi có NaN:
Comparator<Double> wrong = (a, b) ->
        a < b ? -1 : (a > b ? 1 : 0);
~~~

Với **NaN**, cả **a<b** và **a>b** có thể false, khiến comparator coi NaN ngang với nhiều số bình thường, phá luật zero-equivalence consistency.

Dùng:

~~~java
Comparator<Double> correct = Double::compare;
~~~

**Double.compare** quy định thứ tự cho các giá trị double, bao gồm NaN, Infinity và phân biệt **-0.0** với **+0.0**. Nếu nghiệp vụ muốn xử lý NaN hoặc số không hữu hạn theo chính sách khác, định nghĩa quy tắc một cách nhất quán, không chỉ thêm một nhánh tùy tiện có thể phá bắc cầu.

Đối với lớp có trường double, dùng **Comparator.comparingDouble(...)** thay vì trừ hai trường và ép về int.

### 14.3. Null

**Comparator.naturalOrder()** thường không chấp nhận null; nếu nguồn có thể chứa null, quy định thứ tự:

~~~java
Comparator<String> nullsFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());

List<String> values = new ArrayList<>(
        Arrays.asList("b", null, "a")
);

values.sort(nullsFirst);
// values == [null, a, b]
~~~

Đây là **đoạn minh họa**; cần import **Comparator, List, ArrayList, Arrays**. **nullsFirst** xử lý null ở cấp đối tượng được so sánh. Nếu object không null nhưng một **thuộc tính dùng làm key** có thể null, phải cấu hình comparator cho **thuộc tính** đó, ví dụ qua **Comparator.comparing(extractor, Comparator.nullsFirst(...))**.

**Không được tự giả định mọi Comparator phải hỗ trợ null.** Hợp đồng Comparator cho phép một comparator không chấp nhận null và ném NullPointerException theo thiết kế.

### 14.4. Chuỗi, Unicode và locale

**String.compareTo** so sánh theo thứ tự tự nhiên của String, không phải một hệ thống collation theo ngôn ngữ người dùng. Nếu sắp danh sách tên đa ngôn ngữ, hãy có quyết định riêng về **Locale**, **Collator**, dấu, phân biệt hoa/thường và dạng Unicode.

Điểm quan trọng cho bài học này: cho dù chọn thứ tự ngôn ngữ nào, comparator vẫn phải **bắc cầu**, **có lớp bằng 0 ổn định** và phải xác định rõ sự tương thích với **equals** khi đưa vào Set/Map có thứ tự.

## 15. Tính ổn định của comparator: không phụ thuộc trạng thái thay đổi

Một comparator có thể viết đúng cú pháp và dùng phương thức compare an toàn nhưng vẫn **vi phạm hợp đồng về quan hệ thứ tự** nếu kết quả thay đổi giữa các lần so cùng hai object.

Những thiết kế cần tránh:

- Comparator gọi **Random.nextInt(...)** để quyết định thứ tự.
- Comparator dựa vào **System.currentTimeMillis()**, thời điểm đang chạy hoặc thứ tự các thread.
- Comparator dùng một counter mutable rồi đổi quy tắc sau mỗi lần so.
- Comparator phụ thuộc vào một cấu hình/biến global có thể thay đổi trong lúc sắp xếp hoặc trong khi các phần tử đã nằm trong TreeSet/TreeMap.
- Comparator đọc thuộc tính mutable của object mà thread khác có thể sửa không đồng bộ.

**Tính bắc cầu là một tính chất của quan hệ so sánh ổn định trên các giá trị.** Nếu cùng x,y lúc thì trả âm, lúc thì trả dương, các thuật toán sắp xếp không có quan hệ thứ tự nhất quán để duy trì.

Nếu cần sắp theo điểm số thay đổi theo thời gian, có thể:

1. Lấy **snapshot** điểm số/khoá trước khi sort.
2. Sắp những giá trị snapshot bằng comparator thuần.
3. Khi giá trị thay đổi, xây dựng lại kết quả có thứ tự tại một thời điểm dữ liệu nhất quán.

Với **TreeSet/TreeMap**, tránh thay khóa dùng trong comparator mà không xóa và thêm lại theo cơ chế thích hợp.

## 16. Các lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| **return a - b** khi so số nguyên | Overflow, sai dấu, có thể phá phản xứng | **Integer.compare/Long.compare** |
| Comparator vòng tròn | Phá bắc cầu | Chọn thứ tự một chiều, không dùng quan hệ thắng-thua làm sort order |
| Trả 0 khi một cặp "gần đúng" theo tolerance | Có thể phá tính bắc cầu/zero consistency | Xác định nhóm phân loại ổn định hoặc thứ tự có tie-break phù hợp |
| Chỉ so sánh tuổi trong TreeSet<Person> | Người cùng tuổi có thể bị gộp | Thêm tie-break theo định danh nếu muốn giữ từng người |
| Comparator case-insensitive nhưng cần giữ "A" và "a" riêng | TreeSet/TreeMap coi như một khóa | **thenComparing(naturalOrder())** hoặc định nghĩa semantics khác |
| Dùng BigDecimal natural order với yêu cầu phân biệt scale | TreeSet gộp 2.0 và 2.00 | Comparator có tie-break theo scale hoặc chuẩn hóa miền dữ liệu |
| So sánh double bằng phép trừ/nhánh <,> đơn giản | Sai với NaN hoặc tràn/sai số | **Double.compare/comparingDouble** |
| Không xét null trong dữ liệu | NullPointerException | **nullsFirst/nullsLast** hoặc validate |
| Comparator phụ thuộc Random/thời gian/mutable global | Kết quả thay đổi giữa các lần gọi | Comparator thuần, snapshot dữ liệu |
| Dùng comparator khác với comparator đã sort khi binarySearch | Tiền điều kiện tìm kiếm bị vi phạm | Dùng cùng ordering |
| Tưởng thuật toán sort luôn phát hiện comparator sai | Test dễ bỏ lọt lỗi | Test trực tiếp ba luật |
| Tưởng compare==0 luôn đồng nghĩa equals | Mất entry trong TreeSet/TreeMap | Thiết kế quan hệ tương đương rõ ràng |
| Chỉ kiểm tra các cặp | Bỏ sót tính bắc cầu hoặc zero consistency | Kiểm tra các bộ ba x/y/z |
| Gắn tie-break không phù hợp với equals | Vẫn không consistent with equals | So sánh đủ tiêu chí tương đương theo mô hình dữ liệu |

### 16.1. So sánh gần đúng theo epsilon có thể không bắc cầu

Một thiết kế có vẻ hợp lý cho số thực là:

~~~text
"Nếu |x - y| < 0.1 thì coi x == y theo comparator."
~~~

Nhưng có thể:

~~~text
x = 0.00
y = 0.06
z = 0.12

x gần y (< 0.1)
y gần z (< 0.1)
x không gần z (>= 0.1)
~~~

Quan hệ "gần" không bắc cầu, nên **không thể dùng trực tiếp làm quan hệ compare==0 cho comparator cần sắp xếp**. Thay vào đó, tùy nghiệp vụ có thể phân nhóm bằng một **bucket key** xác định (ví dụ nhóm theo bội số bước làm tròn) rồi dùng một comparator nhất quán cho các bucket, có hoặc không có tie-break phụ.

**Phân nhóm gần đúng** và **sắp xếp có total order** là hai yêu cầu khác nhau. Không ép comparator phải giải quyết cả hai bằng một ngưỡng dung sai không có tính bắc cầu.

### 16.2. Đừng viết comparator trả 0 khi chỉ "không thể quyết định"

Một số code kiểu:

~~~java
// RỦI RO: mặc định trả 0 cho các trường hợp chưa xét.
if (specialCase(a, b)) return -1;
return 0;
~~~

Đây là **pseudocode**, vì specialCase/a/b cần được định nghĩa. Cách này có thể coi nhiều đối tượng không thực sự tương đương là cùng lớp, rồi so với một z lại khác hướng. Nếu muốn comparator có hợp đồng rõ ràng, xác định thứ tự đầy đủ của các nhóm/khóa hoặc dùng factory **comparing/thenComparing**.

## 17. Kiểm thử thực tế nên bao gồm gì?

Khi một comparator được dùng trong ứng dụng, đặc biệt với sorted collection, hãy kiểm tra:

1. **Phản xứng** trên các giá trị thường và cực trị int/long.
2. **Bắc cầu** trên nhiều bộ ba, kể cả các giá trị có cùng khóa chính.
3. **Zero consistency** với các cặp comparator trả 0 và các z ở cả hai phía.
4. **Nhất quán với equals**, nếu ứng dụng đòi SortedSet/SortedMap không gộp các đối tượng equals false.
5. **Comparator.compare(x,x)==0** cho mọi x hợp lệ.
6. **null**, NaN, -0.0 và Infinity nếu kiểu dữ liệu có thể chứa chúng.
7. **Dữ liệu Unicode, khác hoa/thường và locale**, nếu sắp chuỗi.
8. **Các object có cùng khóa nhưng khác những trường khác**, đặc biệt với record.
9. **Dữ liệu mutable**: đảm bảo khóa so sánh không đổi trong lúc sort/ở trong TreeSet.
10. **Sort vs Set/Map**: kiểm thử kích thước, contains và get cho các đối tượng compare==0 mà equals false.
11. **Comparator đảo chiều và tie-break**: bảo đảm sau khi compose không xuất hiện một comparator thành phần bị sai luật.
12. **Không kiểm thử bằng cách chờ sort ném lỗi**: test luật comparator trực tiếp.

Một chiến lược hiệu quả là kết hợp **unit test cho ví dụ biên**, **bộ kiểm tra ba phần tử** như mục 8 và **property-based testing** trên những bộ giá trị sinh ngẫu nhiên. Các bài test chỉ tăng độ tin cậy; vẫn cần hiểu và thiết kế một quan hệ có thứ tự đúng từ đầu.

## 18. Bài tập tự kiểm tra

**Câu 1.** Comparator.compare(a,b) có bắt buộc chỉ trả -1, 0 hoặc 1 không?

**Câu 2.** Nếu compare(x,y)>0 và compare(y,z)>0, comparator hợp lệ phải trả gì cho compare(x,z)?

**Câu 3.** Nếu compare(x,y)==0, dấu của compare(x,z) và compare(y,z) phải quan hệ thế nào?

**Câu 4.** Nhất quán với equals có bắt buộc cho mọi Comparator không? Tại sao điều đó quan trọng cho TreeSet?

**Câu 5.** Vì sao comparator **(a,b)->a-b** không an toàn cho Integer?

**Câu 6.** Với BigDecimal **"2.0"** và **"2.00"**, compareTo và equals cho kết quả gì? HashSet/TreeSet mặc định có thể giữ mấy phần tử nếu chỉ thêm hai giá trị ấy?

**Câu 7.** Nếu **String.CASE_INSENSITIVE_ORDER.compare("Java","java")==0**, điều đó có nghĩa **"Java".equals("java")==true** không?

**Câu 8.** Comparator theo tuổi của record Person(name,age) có nhất quán với equals khi hai người cùng tuổi nhưng tên khác nhau không?

**Câu 9.** So sánh gần đúng theo điều kiện **|a-b|<epsilon** rồi trả 0 có luôn là một comparator bắc cầu không?

**Câu 10.** Có thể dùng comparator phụ thuộc Random/time để sort rồi hy vọng kết quả ổn định không?

**Câu 11.** Nếu List.sort không ném lỗi, có thể kết luận comparator tuân thủ mọi luật không?

**Câu 12.** Khi sort một List bằng comparator chỉ xét độ dài, các chuỗi khác nhau nhưng cùng độ dài có bị xóa khỏi List không? Còn nếu thêm vào TreeSet dùng comparator đó?

**Đáp án:**

1. **Không.** Chỉ **dấu âm/0/dương** có ý nghĩa.
2. **compare(x,z)>0**, theo tính bắc cầu.
3. Phải có **cùng dấu** với mọi z, theo zero-equivalence consistency.
4. **Không tuyệt đối bắt buộc**, nhưng cần hiểu compare==0 quyết định tính duy nhất trong TreeSet, có thể khác Object.equals.
5. **Tràn int** có thể đổi dấu và phá phản xứng; dùng **Integer.compare**.
6. **compareTo==0**, **equals==false**; HashSet giữ **2**, TreeSet dùng natural order giữ **1**.
7. **Không.** String.equals vẫn phân biệt hoa/thường; chỉ comparator coi hai chuỗi là ngang nhau.
8. **Không.** Comparator theo tuổi trả 0 khi tuổi bằng nhau, nhưng record.equals còn xét name.
9. **Không.** Quan hệ gần đúng có thể không bắc cầu qua ba số.
10. **Không.** Comparator cần quan hệ so sánh ổn định, tránh phụ thuộc trạng thái thay đổi.
11. **Không.** Thuật toán sort không bảo đảm phát hiện mọi vi phạm.
12. **List.sort chỉ sắp xếp, không xóa phần tử**. TreeSet chỉ giữ một đại diện cho mỗi nhóm mà comparator trả 0.

## 19. Tổng kết và tài liệu tham khảo

**Tính bắc cầu là bắt buộc** để Comparator tạo ra thứ tự nhất quán; còn **nhất quán với equals là một khuyến nghị quan trọng**, đặc biệt khi comparator dùng làm định nghĩa tương đương trong TreeSet/TreeMap. Ngoài tính bắc cầu, Comparator còn phải giữ **phản xứng về dấu** và **zero-equivalence consistency**.

Hãy ưu tiên **Integer.compare**, **Long.compare**, **Double.compare**, **Comparator.comparing...** và **thenComparing...** thay vì tự viết phép trừ hoặc những quy tắc phụ thuộc trạng thái. Khi comparator trả 0, cần hiểu rõ "bằng nhau" được định nghĩa theo **khóa sắp xếp** hay theo **Object.equals**. Và khi nghi ngờ, hãy **kiểm thử các bộ ba giá trị**, không chỉ một cặp hoặc một lần sort.

Tài liệu API Java vẫn còn áp dụng:

- [Comparator — các luật compare, tính bắc cầu và consistent with equals (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [TreeSet — thứ tự và tính nhất quán với equals (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html)
- [TreeMap — khóa được so sánh theo comparator (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeMap.html)
- [SortedSet / SortedMap — ordering và hợp đồng equality (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/SortedSet.html)
- [BigDecimal — compareTo và equals, cohort theo scale (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html)
- [List.sort và Stream.sorted (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
