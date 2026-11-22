# Tính toán dấu phẩy động và giả định về kết quả số

## 1. Vì sao tính toán số là một rủi ro khi chuyển đổi Java?

Trong quá trình **Java Advance Compatibility Migration**, một ứng dụng có thể biên dịch và khởi động thành công trên JDK mới nhưng vẫn trả về những giá trị số khác với môi trường cũ. Điều này đặc biệt đáng chú ý ở phần tính điểm, tính lãi, thống kê, xử lý tín hiệu, tối ưu hóa, đồ họa, mô phỏng, phân tích dữ liệu, machine learning hoặc các quy tắc nghiệp vụ sử dụng float và double.

Một số thay đổi thực tế thường tạo ra câu hỏi:

- Kết quả một phép tính chênh lệch vài đơn vị ở chữ số thập phân cuối cùng sau khi nâng JDK hoặc thay CPU.
- Unit test so sánh hai số double bằng dấu bằng bỗng thất bại khi thay thuật toán, thay framework hoặc bật tính toán song song.
- Tổng tiền được tính từ các giá trị double không bằng tổng dự kiến theo quy tắc thập phân.
- Dữ liệu chứa NaN, Infinity hoặc -0.0 được xử lý, làm tròn, sắp xếp hoặc serialize khác mong đợi.
- Việc thêm Math.fma, tối ưu hóa vòng lặp hoặc thay đổi thứ tự cộng làm thay đổi các bit cuối của kết quả.
- Một hàm toán học từ Math được kỳ vọng luôn cho kết quả giống từng bit trên mọi phiên bản JDK và mọi kiến trúc.

Vấn đề cốt lõi là: **số dấu phẩy động không phải số thực vô hạn độ chính xác**, và không phải mọi cách tính toán biểu diễn cùng một công thức đại số đều tạo ra cùng bit kết quả. Việc migration cần phân biệt thay đổi do đặc tả ngôn ngữ/JVM với thay đổi do thứ tự tính, thuật toán, dữ liệu, thư viện, runtime và môi trường.

Bài học này tập trung vào việc hiểu và kiểm soát những giả định về kết quả số khi nâng Java, thay compiler, chuyển build/runtime hoặc nâng các thư viện xử lý số.

## 2. Hai kiểu số dấu phẩy động nguyên thủy trong Java

Java có hai kiểu nguyên thủy biểu diễn số dấu phẩy động nhị phân:

| Kiểu | Dung lượng | Độ chính xác thường biểu diễn | Ghi chú |
|---|---:|---|---|
| float | 32 bit | Khoảng 6–7 chữ số thập phân có nghĩa | Ít bộ nhớ, dễ tích lũy sai số hơn trong nhiều bài toán. |
| double | 64 bit | Khoảng 15–17 chữ số thập phân có nghĩa | Mặc định thường được dùng cho phép tính số thực. |

Cả float và double dựa trên mô hình IEEE 754 binary floating point, với bit dấu, phần số mũ và phần trị. Tập giá trị biểu diễn hữu hạn, có giới hạn dải số, độ chính xác và các giá trị đặc biệt. Phần lớn số thập phân thông thường không có biểu diễn nhị phân hữu hạn chính xác.

Ví dụ:

~~~java
public final class FloatingPointExample {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println(sum);          // Thường hiển thị 0.30000000000000004
        System.out.println(sum == 0.3);   // false
    }
}
~~~

Giá trị 0.1 và 0.2 là các xấp xỉ nhị phân gần nhất có thể biểu diễn bằng double. Khi cộng rồi làm tròn theo quy tắc floating point, kết quả không nhất thiết trùng biểu diễn của literal 0.3.

Đây không phải lỗi riêng của một JDK. Đây là hệ quả cơ bản của phép tính dấu phẩy động nhị phân; thay runtime không làm các giá trị đó trở thành thập phân chính xác.

### 2.1. Phân biệt giá trị thực, giá trị biểu diễn và chuỗi hiển thị

Trong phân tích kết quả, cần tách ba tầng:

1. **Giá trị toán học lý tưởng:** số thực mà công thức mô tả, chẳng hạn 0.1 + 0.2 = 0.3.
2. **Giá trị dấu phẩy động được lưu:** xấp xỉ IEEE 754 sau khi các phép tính làm tròn.
3. **Chuỗi để in hoặc truyền:** kết quả của Double.toString, String.format, DecimalFormat hoặc bộ serializer.

Thay định dạng hiển thị có thể làm output khác nhau mà bit double không đổi. Ngược lại, hai double khác bit có thể được làm tròn để in thành cùng chuỗi khi giới hạn số chữ số.

Khi điều tra regression, đừng chỉ dựa vào ảnh chụp màn hình hoặc chuỗi hiển thị. Cần biết đang so sánh **giá trị nội bộ**, **bit representation** hay **định dạng đầu ra**.

### 2.2. Kiểm tra bit của một giá trị double

~~~java
double value = 0.1 + 0.2;

long bits = Double.doubleToRawLongBits(value);
System.out.println(Double.toHexString(value));
System.out.printf("bits = 0x%016x%n", bits);
~~~

Double.toHexString mô tả giá trị dấu phẩy động theo dạng hex có thể dùng để đối chiếu. Double.doubleToRawLongBits cho thấy bit pattern thực tế, hữu ích nếu cần tìm khác biệt đúng từng bit.

Lưu ý: Double.doubleToLongBits chuẩn hóa một số biểu diễn NaN; Double.doubleToRawLongBits giữ nguyên raw bit pattern của NaN. Vì vậy phải chọn đúng phương thức nếu mục tiêu là so sánh payload NaN.

## 3. Quy tắc làm tròn và sai số tích lũy

Các phép toán floating point không thực hiện trên số thực vô hạn độ chính xác. Mỗi kết quả phải được biểu diễn trong tập giá trị float hoặc double.

Trong phép toán thông thường, một kết quả lý tưởng không biểu diễn được chính xác sẽ được làm tròn về giá trị có thể biểu diễn gần nhất theo quy tắc áp dụng. Java quy định hành vi các phép toán floating point dựa trên ngữ nghĩa IEEE 754 của ngôn ngữ.

Ví dụ cộng lặp nhiều lần:

~~~java
double total = 0.0;

for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);
System.out.println(total == 1.0);
~~~

Về mặt toán học tổng là 1.0, nhưng phép cộng liên tiếp có thể tích lũy sai số làm tròn; kết quả không cần đúng bit với double literal 1.0.

### 3.1. Sai số tuyệt đối và sai số tương đối

Với giá trị kỳ vọng x và giá trị thực tế y, hai đại lượng thường được dùng:

- Sai số tuyệt đối: |x - y|.
- Sai số tương đối: |x - y| / |x| khi |x| khác 0 và cách so sánh này có ý nghĩa.

Hai thước đo phục vụ các tình huống khác nhau. Sai số tuyệt đối hợp lý gần 0; sai số tương đối hữu ích khi biên độ giá trị thay đổi lớn. Không thể dùng một epsilon cố định cho mọi miền dữ liệu.

Ví dụ sai số tuyệt đối 0.000001 có thể chấp nhận được khi kết quả khoảng 1000000, nhưng rất lớn đối với kết quả kỳ vọng 0.00000001. Ngược lại, điều kiện sai số tương đối có thể không phù hợp tại 0.

### 3.2. ULP là gì?

ULP (unit in the last place) là khoảng cách theo độ phân giải của biểu diễn dấu phẩy động tại một vùng giá trị cụ thể. Java cung cấp Math.ulp(float) và Math.ulp(double) để xem ULP.

~~~java
double a = 1.0;
double b = 1.0e16;

System.out.println(Math.ulp(a));
System.out.println(Math.ulp(b));
~~~

ULP gần giá trị lớn khác đáng kể ULP gần 1.0. Vì vậy không nên kỳ vọng các phép tính ở mọi thang số đều có cùng số chữ số thập phân chính xác.

ULP hữu ích trong kiểm thử hàm số và đánh giá sai lệch sát biểu diễn, nhưng **không phải** một mức dung sai duy nhất áp dụng cho mọi phép toán nghiệp vụ.

## 4. Thứ tự tính toán và tính không kết hợp

Với số thực toán học, phép cộng và phép nhân có tính kết hợp. Với float/double, làm tròn sau mỗi thao tác khiến các biến đổi đại số có thể cho kết quả khác nhau.

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);   // 1.0
System.out.println(right);  // 0.0
~~~

Giải thích:

- Ở nhánh trái, a + b bằng 0.0, rồi cộng c thành 1.0.
- Ở nhánh phải, giá trị c quá nhỏ so với biên độ của b tại độ chính xác double nên b + c có thể làm tròn về b; khi cộng a, kết quả là 0.0.

Điều này dẫn đến hệ quả thực tiễn:

- Đổi thứ tự duyệt một tập dữ liệu có thể làm thay đổi tổng.
- Dùng HashMap/HashSet hoặc thay cách phân vùng dữ liệu có thể thay thứ tự tích lũy.
- Chuyển từ stream tuần tự sang parallel stream có thể thay cây phép cộng.
- Tối ưu hóa thuật toán từ cộng từng phần sang phân nhóm có thể làm khác kết quả.
- Kết quả khác bit không nhất thiết cho thấy code mới sai; cần đánh giá sai lệch theo yêu cầu bài toán.

### 4.1. Parallel stream và phép reduction

Ví dụ:

~~~java
double total = values.parallelStream()
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

Về mặt toán học, các phần tử được cộng lại. Tuy nhiên, phép tổng có thể được chia thành nhiều nhóm để tối ưu hiệu năng và tính chính xác, nên không nên giả định kết quả giống bit với vòng lặp cộng từ trái sang phải.

Ngay cả khi stream tuần tự, implementation của các thao tác tổng có thể sử dụng thuật toán tích lũy khác với vòng lặp thủ công. Java API của phép sum có những cam kết riêng; một migration không nên dựa vào thứ tự cộng nội bộ nếu đó không phải phần hợp đồng được bảo đảm.

Nếu bài toán cần tái lập bit-for-bit, cần kiểm soát thứ tự, thuật toán, cách phân vùng, bộ dữ liệu, compiler/runtime và môi trường. Nếu bài toán chỉ cần độ chính xác theo ngưỡng, nên xác lập dung sai thích hợp và kiểm tra các trường hợp biên.

### 4.2. Ví dụ giảm sai số bằng compensated summation

Một kỹ thuật như Kahan summation có thể giảm sai số khi cộng nhiều giá trị:

~~~java
public static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double adjusted = value - compensation;
        double next = sum + adjusted;
        compensation = (next - sum) - adjusted;
        sum = next;
    }

    return sum;
}
~~~

Kỹ thuật này không biến double thành số thực chính xác và không bảo đảm hoàn toàn độc lập với thứ tự input. Nó là một lựa chọn thuật toán cần đánh giá theo tính chất dữ liệu, không phải cách sửa mọi vấn đề tương thích Java.

## 5. Java trước và sau JDK 17: strictfp và JEP 306

Một khía cạnh quan trọng của migration là quy tắc biểu diễn và đánh giá phép toán dấu phẩy động trong lịch sử Java.

Ở những phiên bản Java trước JDK 17, đặc tả từng cho phép các biểu thức floating point **không strict** sử dụng tập giá trị mũ mở rộng trong một số điều kiện. Từ khóa strictfp cho phép yêu cầu ngữ nghĩa floating point strict theo đặc tả của thời kỳ đó.

Từ **Java 17**, **JEP 306 — Restore Always-Strict Floating-Point Semantics** đưa Java trở về mô hình luôn strict cho các phép toán floating point liên quan. strictfp không còn tạo ra sự khác biệt về ngữ nghĩa tính toán; tùy compiler có thể xuất hiện cảnh báo rằng modifier này không cần thiết.

Ví dụ code legacy:

~~~java
public strictfp class LegacyNumericalEngine {
    public double calculate(double a, double b) {
        return a * b + 1.0;
    }
}
~~~

Trong Java 17+, giữ lại strictfp để bảo toàn source cũ thường không làm thay đổi kết quả phép toán so với bỏ modifier theo mô hình always-strict. Tuy nhiên, không nên suy luận rằng **mọi phép tính trên mọi runtime đều giống từng bit** chỉ vì JEP 306 tồn tại.

### 5.1. JEP 306 giải quyết điều gì?

JEP 306 làm rõ và thống nhất ngữ nghĩa của các phép toán dấu phẩy động trong ngôn ngữ và JVM, giảm khoảng tự do lịch sử liên quan đến tập giá trị mũ mở rộng.

JEP 306 **không** tự động:

- Làm phép cộng double có tính kết hợp như số thực lý tưởng.
- Biểu diễn chính xác 0.1 hoặc các số thập phân tùy ý bằng nhị phân.
- Khiến mọi hàm Math phức tạp có cùng bit trên mọi implementation.
- Làm kết quả của một thuật toán đã đổi thứ tự reduction trở nên giống với bản cũ.
- Chuyển mô hình tính tiền từ double sang decimal chính xác.
- Bảo đảm các thư viện native/JNI hoặc GPU có cùng quy tắc với Java pure code.

Khi so sánh Java 8/11 với Java 17/21, cần ghi rõ sự khác biệt nào do ngữ nghĩa Java, sự khác biệt nào do thuật toán/thư viện, và sự khác biệt nào do CPU hoặc cấu hình runtime.

### 5.2. strictfp trong code cũ

Với project nâng JDK, có thể gặp strictfp ở class, interface hoặc method cũ. Không cần xóa modifier chỉ để chữa một lỗi kết quả số nếu chưa xác định nguyên nhân. Mặt khác, cũng không nên thêm strictfp tràn lan để hy vọng mọi hàm tính toán sẽ hoàn toàn deterministic.

Nếu tổ chức cần hỗ trợ cả JDK cũ và mới, hãy xác định release biên dịch, test matrix và các cam kết numeric compatibility. Khi nhánh mới chỉ còn Java 17+, có thể cân nhắc đơn giản hóa modifier trong một thay đổi riêng, có kiểm thử hồi quy liên quan.

## 6. Math, StrictMath và các phép tính phức tạp

Java có hai lớp tiện ích toán học quan trọng:

- java.lang.Math cung cấp nhiều hàm toán học với các yêu cầu về độ chính xác/hành vi theo tài liệu API. Một số phương thức có thể được tối ưu hóa theo nền tảng hoặc dùng intrinsic.
- java.lang.StrictMath cung cấp các phương thức có đặc tả nhằm hỗ trợ kết quả có tính tái lập mạnh hơn đối với các hàm thuộc phạm vi được quy định, thường dựa trên thuật toán được xác định chặt chẽ hơn.

Với các hàm phức tạp như lượng giác, hàm mũ hoặc logarit, không nên tự giả định Math.sin, Math.cos hoặc Math.exp luôn cho đúng cùng bit giữa mọi phiên bản Java, CPU và cách triển khai. Cần đọc cam kết cụ thể của từng phương thức, nhất là giới hạn về ULP, tính semi-monotonic và trường hợp đặc biệt.

Ví dụ:

~~~java
double x = 0.7;
double a = Math.sin(x);
double b = StrictMath.sin(x);

System.out.println(a);
System.out.println(b);
System.out.println(Double.doubleToRawLongBits(a)
                   == Double.doubleToRawLongBits(b));
~~~

Kết quả so sánh bit phụ thuộc vào phương thức và implementation thực tế. Sự khác biệt rất nhỏ giữa hai giá trị không tự động là lỗi; cần đối chiếu yêu cầu chính xác và phạm vi tính toán của ứng dụng.

### 6.1. Khi nào cân nhắc StrictMath?

StrictMath đáng xem xét khi cần ràng buộc tái lập mạnh với các hàm toán học có quy định tương ứng, chẳng hạn ứng dụng mô phỏng hoặc kiểm thử kết quả giữa các môi trường. Tuy vậy, cần:

1. Kiểm tra cam kết và phiên bản tài liệu API cho từng phương thức đang dùng.
2. Test trên các JDK, CPU và môi trường thực sự được hỗ trợ.
3. Đảm bảo dữ liệu đầu vào, thứ tự phép toán và các phép xử lý ngoài hàm đó không thay đổi.
4. Đánh giá hiệu năng và tính tương thích với mô hình toán học của ứng dụng.

StrictMath không thay thế BigDecimal và cũng không tự xử lý các vấn đề về dữ liệu decimal trong nghiệp vụ tài chính.

### 6.2. Math.fma thay đổi quy tắc làm tròn của biểu thức

FMA (fused multiply-add) tính a × b + c trong một thao tác có một bước làm tròn cho kết quả kết hợp, thay vì làm tròn a × b rồi mới làm tròn tổng.

~~~java
double traditional = a * b + c;
double fused = Math.fma(a, b, c);
~~~

Hai kết quả có thể khác bit. FMA thường mang lợi ích về độ chính xác đối với một số phép tính, nhưng một migration thay a * b + c thành Math.fma(a, b, c) vẫn là **thay đổi thuật toán số** cần test.

Ngược lại, không nên giả định một phép a * b + c trong Java bất kỳ sẽ tự luôn có ngữ nghĩa một lần làm tròn tương đương Math.fma. Khi hợp đồng đòi hỏi FMA, hãy gọi API FMA có ý nghĩa rõ ràng.

## 7. NaN, vô cực và signed zero

IEEE 754 có những giá trị đặc biệt mà nhiều đoạn code nghiệp vụ không dự đoán trước:

- NaN (Not a Number), có thể sinh ra từ một phép toán không xác định như 0.0 / 0.0.
- Positive Infinity và Negative Infinity, ví dụ chia một giá trị khác 0 cho 0.0 hoặc overflow.
- +0.0 và -0.0, có cùng kết quả khi so sánh bằng bằng toán tử == nhưng có thể dẫn đến kết quả khác ở một số phép toán.
- Các giá trị subnormal rất nhỏ, giúp biểu diễn số gần 0 với độ chính xác giảm.

Ví dụ:

~~~java
double nan = 0.0 / 0.0;
double positiveInfinity = 1.0 / 0.0;
double negativeZero = -0.0;

System.out.println(Double.isNaN(nan));           // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(0.0 == negativeZero);         // true
System.out.println(1.0 / 0.0);                   // Infinity
System.out.println(1.0 / negativeZero);          // -Infinity
~~~

### 7.1. NaN không bằng chính nó qua toán tử ==

~~~java
double value = Double.NaN;

System.out.println(value == value);       // false
System.out.println(value != value);       // true
System.out.println(Double.isNaN(value));  // true
~~~

Các phép so sánh quan hệ với NaN như <, <=, >, >= trả về false. Vì thế, một phép kiểm tra giới hạn kiểu:

~~~java
if (value < minimum || value > maximum) {
    throw new IllegalArgumentException("Out of range");
}
~~~

không đủ để chặn NaN: cả hai phép so sánh đều false. Nếu miền dữ liệu chỉ nhận số hữu hạn, hãy kiểm tra rõ ràng:

~~~java
if (!Double.isFinite(value)
        || value < minimum
        || value > maximum) {
    throw new IllegalArgumentException("Non-finite or out of range");
}
~~~

Double.isFinite được cung cấp ở các Java release hiện đại; khi hỗ trợ Java cũ hơn, cần chọn API theo mức Java tối thiểu của dự án.

### 7.2. -0.0 không phải lúc nào cũng tương đương +0.0

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);     // true
System.out.println(Double.compare(positiveZero, negativeZero)); // khác 0
System.out.println(1.0 / positiveZero);               // Infinity
System.out.println(1.0 / negativeZero);               // -Infinity
~~~

Đặc biệt:

- Toán tử == coi +0.0 và -0.0 bằng nhau.
- Double.compare xác lập thứ tự tổng quát riêng, phân biệt signed zero.
- Double.equals cũng phân biệt +0.0 và -0.0 theo bit được quy định cho boxed Double.
- Phép chia có thể cho +Infinity hoặc -Infinity tùy dấu zero.

Vì thế, thay từ so sánh primitive sang boxed Double, comparator, Map key hay sorting có thể làm thay đổi cách xử lý signed zero hoặc NaN.

### 7.3. Boxed Double và các collection

Tương đương toán học không đồng nghĩa với tương đương khi dùng object key.

~~~java
Set<Double> values = new HashSet<>();
values.add(0.0);
values.add(-0.0);

System.out.println(values.size()); // 2 theo equals/hashCode của Double
~~~

Ví dụ trên cần import java.util.Set và java.util.HashSet khi đặt vào một file Java đầy đủ. Trong ứng dụng có aggregation hoặc cache key từ Double, cần quyết định có chuẩn hóa -0.0 thành +0.0 hay không, và cách xử lý NaN trước khi lưu.

Đừng sửa bằng cách dùng toán tử == ở một chỗ và Double.equals ở chỗ khác mà không xác định semantics chung của dữ liệu.

## 8. Overflow, underflow và giới hạn miền giá trị

double có dải số lớn nhưng hữu hạn. Phép tính vượt ngưỡng có thể tạo Infinity; phép tính rất nhỏ có thể làm tròn về 0.0 hoặc giá trị subnormal.

~~~java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = Double.MIN_VALUE / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // 0.0
~~~

Lưu ý Double.MIN_VALUE là số double dương nhỏ nhất lớn hơn 0, **không phải giá trị âm nhỏ nhất**.

Khi chuyển JDK hoặc thay thuật toán, cần kiểm tra những bài toán có giá trị gần các biên:

- Nhân hoặc cộng nhiều giá trị lớn.
- Chia cho số gần 0 hoặc signed zero.
- Chuyển đổi đơn vị tạo hệ số rất lớn hoặc rất nhỏ.
- Normalization và tỷ lệ phần trăm khi tổng bằng 0.
- Hàm exp/log hoặc lượng giác tại vùng có độ nhạy số cao.
- Điều kiện hội tụ trong vòng lặp khi step size nhỏ hơn ULP.

Một thuật toán có thể không ném exception mà vẫn tạo Infinity hoặc NaN rồi lan truyền qua những bước sau. Đối với đường tính nghiệp vụ quan trọng, nên có quy tắc kiểm tra miền hợp lệ và quan sát kết quả không hữu hạn.

## 9. Chuyển đổi kiểu và làm tròn số

### 9.1. Cast double sang int/long

Ép kiểu từ double sang integral type không tương đương với làm tròn thập phân theo nhu cầu nghiệp vụ.

~~~java
double value = 7.9;

int truncated = (int) value;           // 7
long rounded = Math.round(value);      // 8
~~~

Java quy định hành vi chuyển đổi floating point sang số nguyên, bao gồm xử lý NaN và các giá trị vượt phạm vi; việc cast không ném ArithmeticException chỉ vì số vượt dải của kiểu đích. Nếu nghiệp vụ yêu cầu phát hiện vượt ngưỡng, cần kiểm tra riêng trước khi chuyển đổi.

### 9.2. Math.round, floor, ceil và rint

Những hàm sau không thay thế nhau:

| Hàm | Ý nghĩa cơ bản |
|---|---|
| Math.floor(x) | Giá trị nguyên lớn nhất không vượt x, biểu diễn kiểu floating point. |
| Math.ceil(x) | Giá trị nguyên nhỏ nhất không nhỏ hơn x, biểu diễn kiểu floating point. |
| Math.rint(x) | Giá trị nguyên gần nhất ở dạng double, theo quy tắc ties-to-even. |
| Math.round(x) | Làm tròn sang kiểu nguyên theo đặc tả riêng, khác rint ở trường hợp nửa đơn vị. |
| BigDecimal.setScale(scale, mode) | Làm tròn thập phân với số chữ số và quy tắc được chỉ định. |

Ví dụ:

~~~java
double x = 2.5;
double y = -2.5;

System.out.println(Math.rint(x));  // 2.0 (ties to even)
System.out.println(Math.round(x)); // 3
System.out.println(Math.round(y)); // -2
~~~

Với x = -2.5, Math.round và quy tắc “làm tròn ra xa 0 khi ở giữa” không giống nhau. Nếu hệ thống tính tiền hoặc tính mức xếp hạng, phải công bố chính xác quy tắc rounding thay vì chỉ viết “làm tròn gần nhất”.

### 9.3. Số decimal hiển thị

Một kết quả double có thể được format bằng Locale, DecimalFormat hoặc String.format:

~~~java
System.out.printf(Locale.ROOT, "%.2f%n", value);
~~~

Ví dụ này cần import java.util.Locale. Nếu không chỉ định locale, dấu thập phân, dấu phân nhóm hoặc văn bản đầu ra có thể phụ thuộc locale mặc định của môi trường.

Việc format thành hai chữ số thập phân không thay đổi giá trị double đã lưu. Nếu dữ liệu được truyền cho service khác, cần xác định kết quả nào được serialize: số gốc, chuỗi đã format hay một giá trị BigDecimal đã làm tròn theo quy tắc nghiệp vụ.

## 10. Tại sao không nên dùng double cho tiền tệ?

Tài chính thường yêu cầu biểu diễn thập phân chính xác, quy tắc làm tròn cụ thể và khả năng kiểm toán. float/double là nhị phân, nên có thể không biểu diễn chính xác 0.01, 0.1 hoặc tỷ lệ thuế theo dạng thập phân.

Ví dụ:

~~~java
double unitPrice = 0.10;
double tax = 0.20;
double total = unitPrice + tax;

System.out.println(total);
~~~

Đối với tiền tệ, cân nhắc:

1. **long với đơn vị nhỏ nhất** như xu/cent khi miền giá trị, loại tiền và quy tắc làm tròn phù hợp.
2. **BigDecimal** khi cần thập phân chính xác, tỷ lệ, scale và quy tắc rounding rõ ràng.

Không phải mọi phép tính BigDecimal đều tự xác định; phép chia có thể là số thập phân vô hạn tuần hoàn, nên cần chỉ định scale hoặc MathContext.

### 10.1. Tạo BigDecimal đúng cách

~~~java
import java.math.BigDecimal;

public final class MoneyExample {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.10");
        BigDecimal b = new BigDecimal("0.20");
        BigDecimal sum = a.add(b);

        System.out.println(sum); // 0.30
    }
}
~~~

Nên dùng string decimal hoặc BigDecimal.valueOf(double) khi hiểu ý nghĩa của dữ liệu đầu vào. Tránh:

~~~java
BigDecimal a = new BigDecimal(0.1);
~~~

Constructor trên giữ giá trị nhị phân của double 0.1 được chuyển sang biểu diễn thập phân chính xác của chính xấp xỉ đó; nó **không** tạo ra chính xác số thập phân 0.1 như người dùng thường mong muốn.

Ngược lại:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
~~~

Cả hai cách trên thường phù hợp khi muốn mô hình hóa giá trị decimal 0.1, vì valueOf sử dụng biểu diễn chuỗi canonical của double. Tuy nhiên, nếu nguồn đầu vào đã bị làm tròn trong một chuỗi phép tính double, chuyển sang BigDecimal sau đó **không thể khôi phục độ chính xác đã mất**.

### 10.2. Quy tắc làm tròn của BigDecimal

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal subtotal = new BigDecimal("10.005");
BigDecimal rounded = subtotal.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(rounded);
~~~

RoundingMode.HALF_EVEN là lựa chọn phổ biến ở một số bài toán tài chính, nhưng không phải mặc định đúng cho mọi quy định thuế, phí hoặc kế toán. Quy tắc phải xuất phát từ hợp đồng nghiệp vụ.

Phép chia:

~~~java
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
~~~

Nếu chia BigDecimal.ONE cho 3 mà không quy định cách làm tròn, phép chia với biểu diễn thập phân vô hạn có thể gây ArithmeticException. Cần lựa chọn chính sách scale/precision theo miền bài toán.

### 10.3. equals và compareTo của BigDecimal

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));       // false
System.out.println(x.compareTo(y) == 0); // true
~~~

BigDecimal.equals có xét scale, còn compareTo so sánh giá trị số. Khi dùng làm khóa Map hoặc Set, cần biết semantics của equals/hashCode. Chuyển double sang BigDecimal trong migration có thể mang đến thay đổi mới trong so sánh và hashing, không chỉ giải quyết sai số nhị phân.

## 11. Thứ tự sắp xếp, group và key trong dữ liệu số

Ứng dụng có thể thay đổi kết quả sau migration do thuật toán sắp xếp hoặc cấu trúc dữ liệu chứ không chỉ do phép toán.

Ví dụ, một hệ thống tính tổng cho từng nhóm rồi cộng các nhóm:

~~~text
Input cùng giá trị
       │
       ├─ Nhóm theo HashMap ──> duyệt nhóm ──> cộng
       │
       └─ Sắp xếp theo khóa ──> cộng tuần tự
~~~

Nếu thứ tự giá trị được cộng thay đổi, tổng double có thể khác ở chữ số cuối. Sự thay đổi phiên bản thư viện, key partition hoặc số worker có thể làm kết quả thay đổi mà không sửa trực tiếp phép tính cộng.

Một số lưu ý:

- HashMap không công bố thứ tự duyệt cố định như một hợp đồng.
- Parallel reduction có thể nhóm phép cộng theo nhiều cách.
- Double.compare có quy tắc riêng cho NaN và signed zero.
- Primitive == và Double.equals không có cùng semantics cho NaN, +0.0, -0.0.
- Việc sort trước khi cộng đôi khi ảnh hưởng sai số tích lũy và hiệu năng.

Nếu cần kết quả tái lập mạnh, hãy quy định thứ tự input, partitioning và thuật toán tổng; không dựa vào thứ tự ngẫu nhiên của collection.

## 12. Serialization và API contract chứa số

Trong dịch vụ phân tán, lỗi kết quả số thường lộ ra ở ranh giới dữ liệu:

- JSON chứa số nhưng consumer có thể parse thành double, decimal hoặc integer với giới hạn khác nhau.
- Nhiều serializer không hỗ trợ trực tiếp NaN/Infinity như số hợp lệ theo chuẩn JSON.
- Giá trị -0.0 có thể được hiển thị hoặc serialize khác kỳ vọng theo thư viện và cấu hình.
- Một JSON number nguyên lớn có thể vượt độ chính xác số nguyên có thể biểu diễn chính xác bằng double trong client JavaScript.
- XML, CSV và database driver có quy tắc riêng về scale, rounding và special values.
- BigDecimal có thể được xuất thành chuỗi hoặc JSON number tùy config, gây khác kiểu dữ liệu với client.

Không nên tự giả định một giá trị số truyền qua HTTP và quay lại vẫn giữ nguyên bit của double. Contract cần nêu kiểu dữ liệu, đơn vị, precision/scale, cách xử lý null hoặc non-finite và quy tắc round-trip.

Ví dụ, một hợp đồng API tài chính có thể dùng chuỗi decimal:

~~~json
{
  "currency": "USD",
  "amount": "123.45"
}
~~~

Cách làm này yêu cầu consumer parse có kiểm soát và hiểu rõ đây là decimal string. Nếu hệ thống cũ trả JSON number thì việc chuyển sang string là thay đổi wire contract, cần versioning và migration guide; không thể tự ý đổi chỉ vì muốn tăng độ chính xác.

### 12.1. Kiểm tra round-trip

Với các trường dữ liệu quan trọng, nên test:

1. Java object → serializer → payload.
2. Payload → parser của consumer hoặc ứng dụng khác.
3. So sánh theo **hợp đồng**: số decimal, bit double, scale hoặc giá trị làm tròn tùy loại dữ liệu.
4. Giá trị biên: 0, -0.0, cực lớn, cực nhỏ, số có nhiều chữ số, null, NaN/Infinity khi được cho phép.

Nếu contract không cho phép NaN/Infinity, hãy reject hoặc áp dụng quy tắc lỗi rõ ràng, đừng ngầm chuyển thành null hoặc chuỗi không được ghi trong tài liệu.

## 13. Thiết kế test cho kết quả số khi migration

Không tồn tại một phương pháp assert duy nhất phù hợp mọi giá trị float/double. Cần phân loại theo yêu cầu.

### 13.1. Khi cần so sánh chính xác từng bit

Một số trường hợp cần xác nhận serialization nhị phân, định dạng hash, thuật toán deterministic hoặc bitwise reproducibility:

~~~java
long expectedBits = Double.doubleToRawLongBits(expected);
long actualBits = Double.doubleToRawLongBits(actual);

if (expectedBits != actualBits) {
    throw new AssertionError("Different floating-point bits");
}
~~~

Lưu ý:

- Raw-bit comparison phân biệt +0.0/-0.0.
- Nó cũng phân biệt các payload NaN có bit khác nhau.
- Đây là điều kiện chặt chẽ; chỉ dùng khi hợp đồng thực sự yêu cầu bitwise equality.

Nếu muốn so sánh theo semantics của Double.equals hoặc Double.compare, hãy dùng chính semantics đó thay vì thay bằng raw-bit equality.

### 13.2. Khi cần so sánh theo dung sai

Một chiến lược phổ biến là kết hợp dung sai tuyệt đối và tương đối:

~~~java
public static boolean closeEnough(
        double expected,
        double actual,
        double absTolerance,
        double relTolerance) {

    if (Double.doubleToLongBits(expected)
            == Double.doubleToLongBits(actual)) {
        return true;
    }

    if (!Double.isFinite(expected)
            || !Double.isFinite(actual)) {
        return false;
    }

    double difference = Math.abs(expected - actual);
    double scale = Math.max(Math.abs(expected), Math.abs(actual));

    return difference <= absTolerance
            || difference <= relTolerance * scale;
}
~~~

Đây là helper minh họa cho so sánh số hữu hạn theo yêu cầu phù hợp; khi dùng thật cần chọn absTolerance và relTolerance theo miền nghiệp vụ, kiểm soát tham số dung sai âm/NaN và đánh giá overflow của các phép tính phụ. Việc coi expected/actual NaN bằng nhau hay không cũng phải được quyết định rõ trong hợp đồng test.

Nếu framework test cung cấp assertEquals(expected, actual, delta), có thể dùng cho bài toán có dung sai tuyệt đối phù hợp. Không nên đặt delta quá lớn chỉ để mọi regression đều “xanh”.

### 13.3. Test theo invariant

Với các thuật toán không yêu cầu cùng bit, kiểm tra bất biến có ý nghĩa hơn chỉ so sánh output:

- Xác suất thuộc khoảng [0, 1] trong những trường hợp hợp lệ.
- Tổng tỷ lệ gần 1 với dung sai thích hợp.
- Giá trị không âm khi nghiệp vụ yêu cầu, có ngoại lệ đã được định nghĩa.
- Hàm bảo toàn một quan hệ đơn điệu hoặc thứ tự khi miền dữ liệu phù hợp.
- Kết quả sau normalization có norm gần 1.
- Mức sai lệch tối đa nằm dưới ngưỡng khoa học/nghiệp vụ.
- Không xuất hiện NaN hoặc Infinity ở đầu ra mà hợp đồng cấm.

Nếu thuật toán vốn nhạy số, nên có test tại các vùng điều kiện xấu như hai số gần nhau được trừ, giá trị gần overflow, nhiều bước lặp hoặc dữ liệu có biên độ chênh lệch lớn.

### 13.4. Golden tests cần hiểu rõ baseline

Một cách migration thường dùng là chạy cùng dữ liệu trên JDK cũ và mới, lưu kết quả làm baseline.

Tuy nhiên, “kết quả JDK cũ” không tự động là chân lý tuyệt đối. Nếu kết quả cũ có lỗi số hoặc phụ thuộc vào thứ tự không được bảo đảm, đóng băng bit cũ có thể giữ mãi một hành vi không mong muốn. Cần ghi rõ:

1. Bài toán cần bitwise compatibility hay numeric tolerance?
2. Kết quả tham chiếu có được tính từ phương pháp đáng tin cậy hơn không?
3. Input, seed, locale, timezone, thread count và cấu hình runtime có tương đương?
4. Có thay thư viện toán học, bộ giải, vectorization hoặc GPU không?
5. Dung sai đã được owner nghiệp vụ/kỹ thuật phê duyệt chưa?

## 14. Kiểm tra thực nghiệm khi nâng JDK

Một quy trình khảo sát số liệu có thể thực hiện trên ít nhất hai môi trường:

~~~text
Artifact / commit được kiểm soát
                 │
        ┌────────┴─────────┐
        ▼                  ▼
   JDK baseline         JDK mục tiêu
        │                  │
        ▼                  ▼
 Input dataset      Cùng dataset
        │                  │
        ▼                  ▼
 Output + metrics   Output + metrics
        └────────┬─────────┘
                 ▼
    So sánh theo hợp đồng
       (bits/tolerance/
        domain invariants)
                 │
                 ▼
     Phân loại thay đổi
~~~

Thông tin nên ghi kèm mỗi lượt:

| Thông tin | Vì sao cần |
|---|---|
| JDK version đầy đủ, vendor, OS, CPU/architecture | Giúp giải thích khác biệt implementation/môi trường. |
| Commit và artifact checksum | Đảm bảo đang so sánh đúng phiên bản code. |
| Dependency lock/BOM hoặc resolved graph | Tránh nhầm regression do thư viện thay đổi. |
| Input dataset và seed | Có thể tái tạo khi thuật toán có dữ liệu ngẫu nhiên. |
| Thread count, parallelism, batch size | Thứ tự reduction hoặc xử lý phân tán có thể khác. |
| Locale, timezone và định dạng output | Phân biệt thay đổi số với thay đổi biểu diễn chuỗi. |
| Dung sai và loại assertion | Đảm bảo kết luận pass/fail có ngữ nghĩa. |
| Tổng số trường hợp, sai lệch tối đa, số phát hiện non-finite | Cung cấp cái nhìn rộng hơn một giá trị ví dụ. |

### 14.1. Phân loại khác biệt

| Quan sát | Nguyên nhân có thể | Bước tiếp theo |
|---|---|---|
| Khác một vài ULP trong Math.sin/Math.exp | Khác implementation/tối ưu số hoặc cách dùng hàm. | Kiểm tra contract của Math/StrictMath, độ chính xác và test theo ngưỡng. |
| Tổng khác khi bật parallel | Thứ tự/grouping của phép cộng khác. | Chuẩn hóa thuật toán hoặc chấp nhận sai lệch trong giới hạn. |
| Sai khác lớn tại một input nhỏ | Catastrophic cancellation, chia gần 0 hoặc thuật toán không ổn định. | Kiểm tra điều kiện số, lựa chọn công thức/precision tốt hơn. |
| NaN xuất hiện sau thay đổi | Input không hợp lệ, 0/0 hoặc miền hàm vượt phạm vi. | Thêm validation, trace nguồn NaN, xác định error contract. |
| Infinity xuất hiện | Overflow, chia cho 0, exp vượt ngưỡng hoặc tích lũy. | Kiểm tra miền giá trị và xử lý lỗi/ràng buộc input. |
| Số giống nhau nhưng chuỗi khác | Locale, formatter, serializer hoặc quy tắc định dạng thay đổi. | So sánh bit/giá trị trước bước format và kiểm tra wire contract. |
| Tiền lệch một cent | Dùng double, vị trí round khác nhau hoặc quy tắc RoundingMode khác. | Chọn BigDecimal/đơn vị nhỏ nhất và quy định vị trí làm tròn. |
| Output giống trong unit test nhưng production khác | Nguồn input, CPU, concurrency, thư viện native hoặc deployment không tương đương. | Đối chiếu môi trường, checksum và dữ liệu thực tế. |

### 14.2. Không dùng JVM flag như giải pháp thần kỳ

Khi thấy sai lệch, không nên áp dụng đại trà những flag JVM cũ hoặc không rõ tác dụng với hy vọng “khôi phục kết quả Java 8”. Một số flag tối ưu hóa chỉ ảnh hưởng hiệu năng hoặc không còn được hỗ trợ.

Hãy xác định phép toán cụ thể, ngữ nghĩa Java release, JIT/native dependency, độ nhạy số và yêu cầu nghiệp vụ trước khi thay cấu hình runtime. Mọi thay đổi compiler/JVM flag cần được ghi trong baseline và kiểm thử trên toàn bộ môi trường được hỗ trợ.

## 15. Thiết kế thuật toán có tính ổn định số

Khi cần sửa source thay vì chỉ đổi test, hãy ưu tiên các phương pháp có lý do toán học:

### 15.1. Tránh trừ hai số gần bằng nhau khi có công thức khác

Nếu hai giá trị lớn gần bằng nhau được trừ, chữ số có nghĩa có thể bị mất. Hiện tượng này gọi là *cancellation*.

Ví dụ, một công thức có thể đúng đại số nhưng không ổn định với một số input. Cần phân tích miền số và tìm biểu thức tương đương được thiết kế để giảm mất chính xác.

Các API như Math.log1p(x) và Math.expm1(x) tồn tại để hỗ trợ một số trường hợp đầu vào nhỏ mà tính log(1+x) hoặc exp(x)-1 trực tiếp có thể kém chính xác hơn. Chúng không phải thay thế bắt buộc trong mọi tình huống; cần kiểm tra domain và sai số.

### 15.2. Quy định rounding tại ranh giới nghiệp vụ

Trong tính toán giá, nếu quy tắc nghiệp vụ yêu cầu làm tròn sau mỗi dòng hóa đơn, không thể tùy ý dồn mọi phép cộng rồi làm tròn cuối cùng. Ngược lại, làm tròn quá sớm cũng có thể tích lũy sai lệch.

Phải mô tả rõ:

- Đơn vị tính.
- Precision và scale cho mỗi bước.
- RoundingMode.
- Thời điểm làm tròn trước/sau thuế, phí, phân bổ.
- Cách xử lý phần lẻ khi chia một tổng cho nhiều đối tượng.
- Quy tắc đối chiếu tổng thành phần với tổng cuối.

Đây là phần của behavioral contract. Chuyển kiểu từ double sang BigDecimal không có nghĩa kết quả cũ nhất thiết được giữ nguyên; dự án có thể cần thông báo thay đổi nghiệp vụ.

### 15.3. Chọn kiểu dữ liệu theo yêu cầu, không chỉ theo thói quen

| Bài toán | Kiểu/cách tiếp cận thường đáng cân nhắc |
|---|---|
| Mô phỏng khoa học chấp nhận sai số | double, thuật toán ổn định, tolerance được định nghĩa. |
| Dữ liệu cảm biến hoặc đồ họa chú trọng bộ nhớ/throughput | float nếu sai số được chấp nhận. |
| Tiền với đơn vị nhỏ nhất cố định | long và phép kiểm tra overflow khi cần. |
| Thuế, lãi, kế toán thập phân | BigDecimal với MathContext/RoundingMode rõ ràng. |
| Chỉ số tích lũy hàng triệu mẫu | Thuật toán tổng ổn định, thứ tự xử lý và test theo tolerance. |
| Dữ liệu cần bitwise reproducibility | Kiểm soát thuật toán, thứ tự, bit representation và môi trường được chứng nhận. |

Không có lựa chọn duy nhất tối ưu cho độ chính xác, tốc độ, bộ nhớ và tính tái lập. Quyết định phải dựa trên yêu cầu và phép đo thực tế.

## 16. Migration khi thay thư viện toán học và xử lý dữ liệu

Một đợt nâng JDK thường đi cùng nâng thư viện Apache Commons Math, thư viện thống kê, parser JSON, data-processing engine hoặc code native. Kết quả số thay đổi có thể đến từ dependency thay vì chính JDK.

Những thay đổi cần được cô lập:

- Phiên bản thuật toán/hàm của thư viện.
- Quy tắc convergence và stopping criteria.
- Phương pháp cộng/tích lũy hoặc thứ tự duyệt.
- Định dạng serialization.
- Mức precision/mặc định rounding.
- JNI/BLAS/native library, kiến trúc CPU hoặc khả năng vectorization.
- Chính sách với NaN, Infinity và missing data.

Khi có nhiều thay đổi, nên lập ma trận thử nghiệm có kiểm soát, ví dụ:

| Code / library | JDK cũ | JDK mục tiêu | Mục đích |
|---|---|---|---|
| Baseline hiện tại | Chạy | Chạy nếu tương thích | Quan sát ảnh hưởng khi chỉ thay runtime. |
| Library mới | Chạy nếu hỗ trợ | Chạy | Quan sát ảnh hưởng từ việc đổi dependency. |
| Thuật toán được chỉnh sửa | Chạy nếu hỗ trợ | Chạy | Kiểm tra hành vi sau khi đổi code. |

Không nhất thiết mọi tổ hợp đều build/run được; ghi rõ các ô không tương thích. Điều quan trọng là tránh đổ toàn bộ sai lệch lên “Java mới” khi code, dependency và pipeline đã thay đổi đồng thời.

## 17. Quan sát số liệu trong production

Sau rollout, nên theo dõi các chỉ số phản ánh độ tin cậy của kết quả số, không chỉ xem ứng dụng có exception hay không.

Ví dụ:

- Tỷ lệ output không hữu hạn khi hợp đồng chỉ cho phép số hữu hạn.
- Số trường hợp kết quả vượt miền hợp lệ.
- Số mismatch so với nguồn tham chiếu hoặc hệ thống cũ trong cửa sổ đối chiếu an toàn.
- Độ lệch cực đại, p95/p99 của sai lệch theo miền dữ liệu.
- Sai lệch tổng tiền theo đơn vị nhỏ nhất hoặc số trường hợp cần điều chỉnh rounding.
- Thời gian hội tụ và tỷ lệ thuật toán không hội tụ.
- Số bản ghi không serialize được vì NaN/Infinity.

Khi đối chiếu hai implementation xử lý nghiệp vụ, không nên chạy hai thao tác ghi có side effect chỉ để lấy kết quả so sánh. Có thể dùng dữ liệu đã chuẩn hóa, chế độ read-only hoặc shadow computation được thiết kế an toàn.

Một số phát hiện số có thể bị che bởi formatter hay dashboard làm tròn số. Nếu cần điều tra, hãy lưu metric ở độ chính xác đủ dùng, kèm request ID/trace phù hợp, nhưng không đưa bí mật hoặc dữ liệu nhạy cảm vào log.

## 18. Mẫu chính sách numeric compatibility

Khi một module quan trọng được nâng JDK, có thể ghi chính sách rõ ràng:

~~~text
Module: Pricing and Risk Calculation

Input contract:
- Chỉ nhận finite doubles trong dải được xác định.
- NaN và Infinity bị từ chối ở ranh giới API.

Calculation contract:
- Giá tiền được biểu diễn bằng decimal hoặc minor units.
- RoundingMode và vị trí rounding được quy định trong nghiệp vụ.
- Reduction sử dụng thuật toán và thứ tự đã xác định.

Output contract:
- Các trường tiền dùng scale/đơn vị được tài liệu hóa.
- Các trường phân tích sử dụng absolute/relative tolerance phù hợp.
- JSON không chứa NaN/Infinity.

Migration acceptance:
- Regression datasets chạy trên JDK baseline và JDK mục tiêu.
- Các bitwise contract (nếu có) được kiểm tra riêng.
- Các sai lệch numeric khác phải nằm trong ngưỡng đã phê duyệt.
- Các trường hợp biên overflow/underflow/NaN được kiểm tra.

Operational evidence:
- Ghi JDK, dependency, CPU, dataset và version thuật toán.
- Theo dõi mismatch và numeric anomalies sau rollout.
~~~

Đây là mẫu quy trình, không phải các ngưỡng mặc định cho mọi dự án. Mỗi module phải xác định rõ yêu cầu của mình: có bài toán chấp nhận sai số nhỏ, có bài toán tài chính yêu cầu khớp chính xác đến cent, và có giao thức yêu cầu giữ nguyên bit pattern.

## 19. Những giả định sai thường gặp

| Giả định | Vì sao sai hoặc thiếu | Cách tiếp cận |
|---|---|---|
| “0.1 + 0.2 luôn bằng 0.3 trong double.” | Nhiều decimal không biểu diễn chính xác bằng binary floating point. | So sánh theo hợp đồng và dùng decimal khi cần. |
| “Đổi dấu ngoặc không đổi kết quả.” | Phép toán floating point không kết hợp như số thực. | Kiểm soát thứ tự và test numeric tolerance. |
| “Math luôn giống bit trên mọi JVM.” | Một số hàm có phạm vi sai số và implementation khác nhau. | Xem API contract, kiểm thử và cân nhắc StrictMath khi phù hợp. |
| “strictfp sẽ sửa mọi sai lệch Java 17/21.” | JEP 306 đã đưa semantics luôn strict; sai lệch có nhiều nguyên nhân khác. | Phân tích thuật toán, Math functions và môi trường. |
| “Cộng song song bằng tổng tuần tự.” | Cây reduction và thứ tự cộng có thể khác. | Chọn thuật toán và yêu cầu tái lập cụ thể. |
| “NaN bị chặn bởi x < min hoặc x > max.” | So sánh quan hệ với NaN đều false. | Kiểm tra Double.isFinite hoặc isNaN trước. |
| “0.0 và -0.0 luôn như nhau.” | Signed zero ảnh hưởng bit, compare và phép chia. | Quy định chính sách xử lý signed zero. |
| “Double.equals và == hoàn toàn tương đương.” | NaN và signed zero có semantics khác giữa wrapper và primitive. | Chọn comparator/equals theo hợp đồng. |
| “BigDecimal tự động chính xác nếu tạo từ double.” | new BigDecimal(double) giữ xấp xỉ binary đầu vào. | Tạo từ string decimal hoặc valueOf khi phù hợp. |
| “BigDecimal.equals là so sánh số.” | equals xét scale, compareTo không xét scale như vậy. | Phân biệt identity và numeric equality. |
| “In 2 chữ số nghĩa là đã làm tròn dữ liệu.” | Formatting không đổi giá trị đã lưu. | Round tại bước nghiệp vụ hoặc lưu kiểu decimal. |
| “Một epsilon cố định dùng cho mọi phép tính.” | Biên độ và độ nhạy số thay đổi theo miền dữ liệu. | Chọn ngưỡng tuyệt đối/tương đối hoặc ULP theo bài toán. |
| “Không có exception nghĩa là phép tính đúng.” | Overflow có thể cho Infinity, phép toán không xác định cho NaN. | Kiểm tra miền và invariants. |
| “Chênh lệch trên JDK mới là lỗi JDK.” | Dependency, dữ liệu, thứ tự tính, formatter hoặc native stack có thể khác. | Tách biến số và chạy thí nghiệm có kiểm soát. |

## 20. Quy trình xử lý một regression kết quả số

Khi xuất hiện kết quả khác sau migration:

1. **Ghi nhận hiện tượng:** input, expected/actual, phiên bản JDK, sai lệch tuyệt đối/tương đối, output định dạng và bit nếu cần.
2. **Xác định hợp đồng:** yêu cầu bitwise equality, tolerance, số thập phân chính xác hay invariant?
3. **Tách phạm vi thay đổi:** JDK, library, compiler, CPU, dữ liệu, concurrency, locale, formatter và deployment.
4. **Tạo trường hợp tối thiểu:** đoạn code/dataset đủ tái hiện sai lệch không phụ thuộc toàn bộ hệ thống.
5. **Kiểm tra special values:** NaN, Infinity, signed zero, overflow/underflow, subnormal.
6. **Kiểm tra thứ tự tính:** reduction, parallelism, iteration order, FMA và rounding boundary.
7. **Kiểm tra thư viện toán học:** Math/StrictMath, native library, phiên bản thuật toán.
8. **Đánh giá giải pháp:** sửa công thức, dùng thuật toán ổn định, thay kiểu dữ liệu, hoặc thay chiến lược test theo đúng hợp đồng.
9. **Chạy regression và integration tests:** trên môi trường baseline và JDK mục tiêu, với boundary dataset.
10. **Quyết định rollout:** cập nhật numeric compatibility policy, metrics, rollback và tài liệu nếu kết quả nghiệp vụ thay đổi.

Nếu phát hiện sai lệch trong phép tính tiền/thuế hoặc dữ liệu giao tiếp, không nên tự ý “nới tolerance” để làm test xanh. Cần có đánh giá nghiệp vụ và migration plan vì chênh lệch nhỏ có thể tích lũy hoặc gây sai lệch đối soát.

## 21. Kết luận

Khi nâng JDK, tính toán dấu phẩy động cần được đánh giá theo **ngữ nghĩa IEEE 754, độ chính xác biểu diễn, thứ tự phép toán, hàm Math/StrictMath, strictfp và môi trường thực thi**. Java 17 với JEP 306 khôi phục semantics always-strict cho phép toán floating point, nhưng không biến double thành số thập phân chính xác hay xóa bỏ sự khác biệt do thuật toán, song song hóa và thư viện.

Một chiến lược migration an toàn phải phân biệt kết quả số thực lý tưởng với bit floating point và chuỗi được serialize; xác định rõ yêu cầu bitwise, tolerance hoặc decimal exactness; kiểm tra NaN/Infinity/-0.0, overflow/underflow; và dùng BigDecimal hoặc đơn vị tiền nhỏ nhất khi hợp đồng yêu cầu thập phân chính xác. Bằng chứng nên được thu thập từ cùng dataset, artifact, JDK và dependency đã kiểm soát, kết hợp regression tests, invariants và quan sát production.

**Đích đến không phải là buộc mọi phép tính trên JDK mới cho ra cùng chuỗi số với JDK cũ bằng mọi giá, mà là bảo đảm kết quả đáp ứng hợp đồng số đã định nghĩa, có thể giải thích được khác biệt và có cơ sở kiểm chứng khi triển khai.**
