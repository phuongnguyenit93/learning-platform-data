# Float và Double trong Java: NaN, +0.0 và -0.0

## 1. Tại sao quan trọng với hợp đồng đối tượng?

Java có hai kiểu dấu chấm động nguyên thủy là **float** (32 bit) và **double** (64 bit), cùng hai lớp bao tương ứng **Float** và **Double**. Ngay cả khi hai giá trị mang ý nghĩa số học giống nhau, phép so sánh **nguyên thủy bằng ==** có thể khác với phương thức **equals(Object)** của lớp bao, đặc biệt ở **NaN** và **số không có dấu**.

- **NaN (Not a Number):** hai giá trị NaN so bằng == trên số thực nguyên thủy cho kết quả false, nhưng các lớp bao Float/Double coi các NaN là bằng nhau theo equals.
- **+0.0 và -0.0:** số thực nguyên thủy coi chúng bằng nhau theo ==, nhưng lớp bao phân biệt chúng trong equals.
- Phương thức compare/compareTo của Float/Double được thiết kế nhất quán với equals lớp bao, chứ không chỉ dùng toán tử < hoặc > trên số thực.
- Các phương thức hashCode của lớp bao tuân theo đúng quy tắc equals, vì HashSet/HashMap phụ thuộc vào hợp đồng equals–hashCode.

Vì vậy, khi tự viết equals và hashCode cho đối tượng có trường float/double, cần quyết định **quan hệ bằng nhau mong muốn** và xử lý cả NaN lẫn signed zero. Các ví dụ bên dưới dùng Java 17+.

## 2. NaN: giá trị đặc biệt và toán tử số thực nguyên thủy

NaN biểu thị một kết quả không phải số thực xác định theo IEEE 754. Ví dụ:

~~~java
double a = 0.0d / 0.0d;
double b = Math.sqrt(-1.0d);
float c = 0.0f / 0.0f;
~~~

Những phép tính dấu chấm động trên tạo NaN; chúng không ném ArithmeticException như phép chia số nguyên cho 0. Hằng sẵn có: **Double.NaN** và **Float.NaN**.

Với một giá trị double n = Double.NaN:

| Biểu thức | Kết quả |
| --- | --- |
| n == n | false |
| n != n | true |
| n < 1.0 | false |
| n > 1.0 | false |
| n <= 1.0 | false |
| n >= 1.0 | false |
| Double.isNaN(n) | true |

Bất kỳ so sánh thứ tự nguyên thủy nào có NaN cũng trả false. Đây là lý do các biểu thức phủ định của phép so sánh không đủ để suy ra thứ tự khi dữ liệu có thể chứa NaN.

**Nhận biết NaN đúng mục đích:**

~~~java
boolean isDoubleNaN = Double.isNaN(a);
boolean isFloatNaN = Float.isNaN(c);
~~~

Có thể dùng a != a để nhận biết NaN ở số nguyên thủy, nhưng Double.isNaN/Float.isNaN truyền đạt chủ ý rõ ràng hơn. NaN không phải vô cực; dùng Double.isInfinite/Float.isInfinite khi cần xác định Infinity hoặc -Infinity.

## 3. Số không có dấu: +0.0 và -0.0

IEEE 754 có hai biểu diễn số không, khác nhau ở bit dấu:

- **+0.0**: bit dấu 0.
- **-0.0**: bit dấu 1.

Với các toán hạng số thực nguyên thủy, hai giá trị này được coi là bằng nhau:

~~~java
System.out.println(+0.0d == -0.0d); // true
System.out.println(1.0d / +0.0d);    // Infinity
System.out.println(1.0d / -0.0d);    // -Infinity
~~~

Chúng bằng nhau theo == nhưng phép chia có thể cho vô cực khác dấu. Đây là lý do phần biểu diễn dấu không phải chi tiết vô nghĩa trong mọi ứng dụng.

Có thể quan sát bit bằng các API:

~~~java
Double.doubleToRawLongBits(+0.0d); // 0L
Double.doubleToRawLongBits(-0.0d); // Long.MIN_VALUE
Float.floatToRawIntBits(+0.0f);   // 0
Float.floatToRawIntBits(-0.0f);   // Integer.MIN_VALUE
~~~

Các đoạn này minh họa biểu thức trong một ngữ cảnh Java; chưa phải một lớp chương trình đầy đủ. Hai phương thức có chữ Raw giữ nguyên bit của biểu diễn. Phương thức không có chữ Raw cũng giữ khác biệt signed zero, nhưng chuẩn hóa các mẫu bit NaN.

## 4. Float.equals() và Double.equals() có quy tắc riêng

Hợp đồng của lớp bao là:

- **Double.equals(Object)** chỉ true khi đối số cũng là Double và hai giá trị có cùng bit theo **Double.doubleToLongBits**.
- **Float.equals(Object)** chỉ true khi đối số cũng là Float và hai giá trị có cùng bit theo **Float.floatToIntBits**.

Hai hàm chuyển bit **chuẩn hóa mọi giá trị NaN** thành một biểu diễn NaN quy ước. Vì vậy các NaN khác payload vẫn được equals coi là bằng nhau. Riêng +0.0 và -0.0 có bit dấu khác nên **không bằng nhau theo wrapper equals**.

| Cặp số cùng kiểu | == trên nguyên thủy | equals của lớp bao |
| --- | --- | --- |
| 1.5 và 1.5 | true | true |
| NaN và NaN | false | true |
| +0.0 và -0.0 | true | false |
| +0.0 và +0.0 | true | true |
| -0.0 và -0.0 | true | true |
| Infinity và Infinity | true | true |
| Infinity và -Infinity | false | false |

Ví dụ:

~~~java
double n1 = Double.NaN;
double n2 = 0.0d / 0.0d;
System.out.println(n1 == n2); // false
System.out.println(Double.valueOf(n1).equals(Double.valueOf(n2))); // true

double pz = +0.0d;
double nz = -0.0d;
System.out.println(pz == nz); // true
System.out.println(Double.valueOf(pz).equals(Double.valueOf(nz))); // false
~~~

Cần phân biệt thêm **== giữa hai tham chiếu lớp bao**: nếu cả hai toán hạng là đối tượng Double (hoặc Float), == so sánh **danh tính đối tượng**, không phải giá trị. Nếu một toán hạng nguyên thủy, Java có thể thực hiện unboxing, và unboxing giá trị null gây NullPointerException. Khi đọc biểu thức, luôn xem chính xác kiểu của hai vế.

**Float.equals không thể coi Double là bằng nhau**, và ngược lại, kể cả hai đối tượng có cách hiển thị gần giống nhau. Đây là hai lớp khác kiểu.

## 5. So sánh thứ tự: compare và compareTo

**Double.compare(x, y)** và **Float.compare(x, y)** dùng một thứ tự đầy đủ tương thích với equals lớp bao:

1. Mọi NaN cùng kiểu được coi tương đương nhau khi so sánh: compare(NaN, NaN) bằng 0.
2. NaN đứng lớn hơn mọi giá trị số, kể cả +Infinity.
3. -0.0 đứng nhỏ hơn +0.0.
4. Với số thông thường và các vô cực, thứ tự số học tự nhiên được duy trì.

Ví dụ:

~~~java
Double.compare(Double.NaN, Double.NaN);             // 0
Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // 1
Double.compare(-0.0d, +0.0d);                        // -1
Float.compare(-0.0f, +0.0f);                        // -1
~~~

Các hàm compare trả số âm, 0 hoặc số dương; với các cặp ghi ở đây, kết quả Java cụ thể lần lượt là 0, 1, -1, -1. CompareTo của lớp bao dùng cùng quy tắc.

Để sắp xếp Double/Float, ưu tiên các comparator rõ ràng:

~~~java
// Chỉ là khai báo minh họa, yêu cầu import java.util.Comparator.
Comparator<Double> doubleComparator = Double::compare;
Comparator<Float> floatComparator = Float::compare;
~~~

**Lỗi thường gặp:**

~~~java
// Sai: mất phần thập phân, lỗi với NaN và signed zero.
Comparator<Double> bad = (a, b) -> (int) (a - b);

// Cũng không phù hợp với wrapper equals khi chứa NaN/signed zero.
Comparator<Double> bad2 = (a, b) -> a < b ? -1 : a > b ? 1 : 0;
~~~

Bộ so sánh thứ hai có thể trả 0 dù một bên NaN và bên còn lại là số bình thường; hoặc trả 0 cho hai signed zero. Với **TreeSet** hoặc **TreeMap**, comparator quyết định xem hai khóa có cùng vị trí logic hay không qua kết quả compare == 0, nên comparator khác quy tắc equals có thể gây hành vi ngạc nhiên so với HashSet/HashMap.

## 6. HashCode của Float và Double: tính tương thích bắt buộc

Hai đối tượng bằng nhau theo equals phải có cùng hashCode. Các phương thức **Double.hashCode(double)** và **Float.hashCode(float)** được thiết kế tương thích với quy tắc lớp bao:

- Mọi NaN cùng kiểu được chuẩn hóa nên có hash giống nhau.
- +0.0 và -0.0 có bit dấu khác nên hash khác nhau.
- Không yêu cầu hai giá trị không bằng nhau phải có hash khác nhau: va chạm băm vẫn hợp lệ.

Một số kết quả cụ thể:

~~~java
Double.hashCode(+0.0d); // 0
Double.hashCode(-0.0d); // Integer.MIN_VALUE
Float.hashCode(+0.0f);  // 0
Float.hashCode(-0.0f);  // Integer.MIN_VALUE
~~~

Điều này nhất quán với Double.equals/Float.equals vì các phương thức equals **phân biệt** signed zero.

Ví dụ bộ sưu tập:

~~~java
// Đoạn minh họa trong ngữ cảnh đã import Set và HashSet.
Set<Double> values = new HashSet<>();
values.add(Double.NaN);
values.add(Double.NaN); // Trùng theo Double.equals.
values.add(+0.0d);
values.add(-0.0d);       // Khác theo Double.equals.
System.out.println(values.size()); // 3
~~~

HashSet có một phần tử NaN và hai phần tử số không khác dấu. Nếu thay bằng HashSet<Float> thì nguyên tắc tương tự.

**Không nên** dùng Double.doubleToRawLongBits hoặc Float.floatToRawIntBits trực tiếp làm nền để tự băm đối tượng mà equals lại gộp mọi NaN; các NaN mang bit thô khác nhau có thể tạo hash khác nhau dù equals true. Các hàm doubleToLongBits/floatToIntBits chuẩn hóa NaN và phù hợp hơn nếu thực hiện quy tắc lớp bao.

## 7. Chương trình Java 17+ có thể biên dịch/chạy

Lưu đúng tên **FloatingEqualityDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double nanA = Double.NaN;
        double nanB = 0.0d / 0.0d;
        double positiveZero = +0.0d;
        double negativeZero = -0.0d;

        System.out.println("double NaN == NaN: " + (nanA == nanB));
        System.out.println("Double.equals NaN: "
                + Double.valueOf(nanA).equals(Double.valueOf(nanB)));
        System.out.println("Double.compare NaN: "
                + Double.compare(nanA, nanB));
        System.out.println("Double.isNaN: " + Double.isNaN(nanA));
        System.out.println("NaN hashes equal: "
                + (Double.hashCode(nanA) == Double.hashCode(nanB)));

        System.out.println("double +0 == -0: "
                + (positiveZero == negativeZero));
        System.out.println("Double.equals zeros: "
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("Double.compare(-0,+0): "
                + Double.compare(negativeZero, positiveZero));
        System.out.println("Zero hashes differ: "
                + (Double.hashCode(positiveZero)
                        != Double.hashCode(negativeZero)));

        Set<Double> doubles = new HashSet<>();
        doubles.add(nanA);
        doubles.add(nanB);
        doubles.add(positiveZero);
        doubles.add(negativeZero);
        System.out.println("HashSet<Double> size: " + doubles.size());

        System.out.println("Arrays.equals double NaNs: "
                + Arrays.equals(new double[] {nanA},
                        new double[] {nanB}));
        System.out.println("Arrays.equals double zeros: "
                + Arrays.equals(new double[] {positiveZero},
                        new double[] {negativeZero}));

        float floatNanA = Float.NaN;
        float floatNanB = 0.0f / 0.0f;
        float floatPositiveZero = +0.0f;
        float floatNegativeZero = -0.0f;

        System.out.println("float NaN == NaN: "
                + (floatNanA == floatNanB));
        System.out.println("Float.equals NaN: "
                + Float.valueOf(floatNanA)
                        .equals(Float.valueOf(floatNanB)));
        System.out.println("Float.compare NaN: "
                + Float.compare(floatNanA, floatNanB));
        System.out.println("float +0 == -0: "
                + (floatPositiveZero == floatNegativeZero));
        System.out.println("Float.equals zeros: "
                + Float.valueOf(floatPositiveZero)
                        .equals(Float.valueOf(floatNegativeZero)));
        System.out.println("Float.compare(-0,+0): "
                + Float.compare(floatNegativeZero, floatPositiveZero));
        System.out.println("Float zero hashes differ: "
                + (Float.hashCode(floatPositiveZero)
                        != Float.hashCode(floatNegativeZero)));
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 FloatingEqualityDemo.java
java FloatingEqualityDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
double NaN == NaN: false
Double.equals NaN: true
Double.compare NaN: 0
Double.isNaN: true
NaN hashes equal: true
double +0 == -0: true
Double.equals zeros: false
Double.compare(-0,+0): -1
Zero hashes differ: true
HashSet<Double> size: 3
Arrays.equals double NaNs: true
Arrays.equals double zeros: false
float NaN == NaN: false
Float.equals NaN: true
Float.compare NaN: 0
float +0 == -0: true
Float.equals zeros: false
Float.compare(-0,+0): -1
Float zero hashes differ: true
~~~

Giải thích:

1. Hai NaN không bằng nhau theo == nguyên thủy, nhưng bằng nhau theo wrapper equals, có compare bằng 0 và hash giống nhau.
2. Hai signed zero bằng nhau theo == nhưng khác theo wrapper equals, compare và hash.
3. HashSet<Double> chỉ chứa một NaN (bất kể cách tạo) và hai số không khác dấu.
4. **Arrays.equals(double[], double[])** và bản float[] sử dụng quy tắc so sánh phần tử phù hợp với các bit chuẩn hóa: các NaN tương đương nhau, hai signed zero khác nhau. Không thể hiểu rằng mọi trường hợp so sánh mảng số thực đều áp dụng == nguyên thủy.

Chương trình này là ví dụ độc lập; các khối mã ngắn ở những phần trước chỉ minh họa cách hoạt động của API.

## 8. Viết equals/hashCode cho lớp có trường double hoặc float

Nếu lớp **Sample** có trường double value và muốn quan hệ bằng nhau giống Double.equals, nên dùng cặp:

~~~java
// Đặt trong lớp Sample, giả định lớp final và có trường double value.
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Sample other)) {
        return false;
    }
    return Double.compare(value, other.value) == 0;
}

@Override
public int hashCode() {
    return Double.hashCode(value);
}
~~~

Đây là trích đoạn trong lớp, không phải chương trình chạy độc lập. Với float, dùng **Float.compare** và **Float.hashCode** tương ứng. Kiểm tra cùng tham chiếu, null và loại đối tượng vẫn quan trọng; với hệ phân cấp có kế thừa, còn cần xử lý quan hệ đối xứng/bắc cầu khi mở rộng equals.

**Vì sao không dùng == trong equals rồi Double.hashCode trong hashCode?** Nếu equals xét primitive value == other.value, hai đối tượng chứa +0.0 và -0.0 sẽ bằng nhau nhưng nhận hashCode khác nhau. Như vậy vi phạm điều kiện **equals true kéo theo hash bằng nhau**.

Với NaN, phép == luôn false, nên một cài đặt ngây thơ thiếu bước cùng tham chiếu còn có thể khiến một đối tượng chứa NaN **không bằng chính nó**, vi phạm phản xạ của equals.

### 8.1. Khi nghiệp vụ muốn gộp +0.0 và -0.0

Không phải mọi lớp giá trị bắt buộc phải giữ chính sách signed zero của Double.equals. Nếu bài toán coi +0.0 và -0.0 cùng một giá trị, cần chuẩn hóa **trước cả so sánh lẫn băm**:

~~~java
// Các phương thức minh họa bên trong lớp Measurement final
// có trường double value không đổi.
private static double normalizeZero(double x) {
    return x == 0.0d ? 0.0d : x;
}

@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Measurement other)) {
        return false;
    }
    return Double.doubleToLongBits(normalizeZero(value))
            == Double.doubleToLongBits(normalizeZero(other.value));
}

@Override
public int hashCode() {
    return Double.hashCode(normalizeZero(value));
}
~~~

Quy tắc tùy chỉnh này gộp hai signed zero và vẫn coi mọi NaN là bằng nhau. Việc chuẩn hóa ở **cả hai phương thức** giữ đúng hợp đồng hash. Nếu cần sắp xếp những đối tượng Measurement này, comparator cũng phải dùng cùng quy tắc nếu muốn compare == 0 tương đương với equals.

Nếu dùng một **record** có component float/double, Java sinh ra equals/hashCode theo quy tắc phân biệt signed zero và coi NaN tương đương. Khi cần equality tùy biến, không được chỉ thay đổi equals mà bỏ quên hashCode.

### 8.2. Tránh dùng so sánh gần đúng làm equals

Công thức kiểu trị tuyệt đối của hiệu nhỏ hơn epsilon thường hữu ích để kiểm tra *gần bằng nhau* trong tính toán. Nhưng nếu dùng trực tiếp làm Object.equals, nó có thể vi phạm **tính bắc cầu**: a gần b, b gần c nhưng a không gần c. Cách kiểm tra gần đúng cũng cần xử lý NaN/vô cực và tràn số thích hợp.

Hãy tạo phương thức riêng như **approximatelyEqual(a, b, tolerance)** cho nhu cầu dung sai, hoặc định nghĩa phép lượng tử hóa thành các nhóm giá trị có quan hệ bằng nhau và hash phù hợp nếu thực sự cần đối tượng làm khóa băm.

## 9. Cách chọn API theo nhu cầu

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Xác định có phải NaN | Double.isNaN / Float.isNaN |
| Kiểm tra nguyên thủy theo toán tử IEEE | ==, !=, <, > với float/double |
| So sánh đối tượng wrapper | Double.equals / Float.equals |
| Xếp thứ tự tương thích với wrapper equals | Double.compare / Float.compare |
| Băm phù hợp wrapper | Double.hashCode / Float.hashCode |
| So sánh mảng float[]/double[] | Arrays.equals |
| Băm mảng theo phần tử | Arrays.hashCode |
| Phân biệt bit dấu số không | doubleToRawLongBits / floatToRawIntBits |
| Gộp signed zero theo yêu cầu nghiệp vụ | Chuẩn hóa thống nhất trong equals, hashCode và comparator |
| Kiểm tra số thực gần nhau theo dung sai | Phương thức riêng, không tùy tiện thay cho Object.equals |

## 10. Những nhầm lẫn cần tránh

**“Hai NaN là hai giá trị khác nhau trong mọi ngữ cảnh.”** Không đúng: == nguyên thủy trả false, nhưng wrapper equals trả true cho mọi NaN cùng kiểu và compare trả 0.

**“+0.0 và -0.0 bằng nhau nên hai Double phải equals.”** Không đúng: == nguyên thủy trả true, Double.equals phân biệt dấu để tạo ra quy tắc đối tượng ổn định với hash và thứ tự.

**“Nếu Double.compare(x, y) == 0 thì x == y trên số nguyên thủy.”** Không đúng với NaN. Cặp compare == 0 tương đương quan hệ wrapper equals của cùng kiểu.

**“Nếu khác nhau theo equals thì hashCode phải khác.”** Không đúng: collision được phép. Nhưng hai giá trị bằng nhau theo equals bắt buộc có cùng hash.

**“Tự băm bit thô sẽ luôn đúng.”** Không đúng nếu equals gộp các NaN khác payload hoặc gộp signed zero. Chỉ dùng một cách băm nhất quán với quan hệ bằng nhau đã chọn.

**“Bỏ kiểm tra cùng tham chiếu không gây sao vì chỉ có trường số.”** Nguy hiểm nếu equals dùng == với NaN, làm mất tính phản xạ.

**“Dùng Comparator tùy ý không ảnh hưởng collection.”** Không đúng đối với TreeSet/TreeMap: compare == 0 quyết định đồng nhất khóa trong tập/sơ đồ có thứ tự, đôi khi khác với equals.

## 11. Checklist kiểm thử

Khi kiểm thử lớp chứa float/double, nên kiểm tra tất cả tình huống:

1. **Tự so sánh:** x.equals(x) luôn true, kể cả khi x chứa NaN.
2. **Hai đối tượng có NaN:** kết quả theo quy tắc đã công bố; nếu dùng wrapper semantics thì true.
3. **Hai signed zero:** kết quả theo quy tắc đã công bố; wrapper semantics phân biệt, custom normalized semantics thì gộp.
4. **Tính băm:** mọi cặp equals true đều phải có hashCode bằng nhau.
5. **So sánh thứ tự:** nếu có comparator/Comparable, xem compare == 0 có phản ánh cùng quan hệ bằng nhau như thiết kế không.
6. **Collection:** thêm NaN và hai signed zero vào HashSet/TreeSet rồi kiểm tra số phần tử phù hợp quy tắc so sánh.
7. **Giữ nguyên dữ liệu:** equals/hashCode không cho kết quả ngẫu nhiên khi trạng thái so sánh không đổi.
8. **Phân biệt kiểu:** Float.equals(Double) luôn false; không suy luận bằng nhau từ chuỗi in ra giống nhau.
9. **Số thường, vô cực, null:** kiểm tra trường hợp không có NaN hoặc signed zero vẫn tuân thủ hợp đồng.
10. **Đối tượng bất biến:** tránh thay đổi trường dùng trong equals/hashCode sau khi dùng làm khóa HashMap/HashSet.

**Ghi nhớ:** với số thực nguyên thủy, NaN không bằng NaN và +0.0 bằng -0.0 theo ==; với wrapper Float/Double, **NaN bằng NaN còn hai signed zero khác nhau**. Thiết kế equals, hashCode và comparator theo cùng một quy tắc để bộ sưu tập và phép so sánh hoạt động nhất quán.