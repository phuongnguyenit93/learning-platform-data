# Always-strict từ Java 17 và vai trò lịch sử của `strictfp`

Từ **Java SE 17**, các biểu thức dấu phẩy động `float` và `double` được đánh giá **luôn theo ngữ nghĩa strict** (*always-strict floating-point semantics*). Đây là thay đổi của **JEP 306 – Restore Always-Strict Floating-Point Semantics**. Vì vậy, trên Java 17 trở lên, thêm hay bỏ từ khóa `strictfp` **không làm thay đổi kết quả đánh giá một biểu thức dấu phẩy động**.

Trước Java 17, đặc biệt trong Java 1.2 đến Java 16, `strictfp` từng có tác dụng: nó yêu cầu các phép tính trong phạm vi áp dụng tuân thủ đúng tập giá trị `float`/`double` chuẩn, thay vì cho phép một số JVM sử dụng tập giá trị trung gian có **miền số mũ mở rộng**. Thay đổi từ Java 17 loại bỏ khác biệt này.

Ví dụ quan trọng:

```java
static double ordinary(double x) {
    return x * 2.0 / 2.0;
}

static strictfp double legacyStrict(double x) {
    return x * 2.0 / 2.0;
}
```

Hai phương thức trên có **cùng ngữ nghĩa dấu phẩy động trên Java 17+**. `strictfp` vẫn được chấp nhận trong source code nhằm tương thích, nhưng trình biên dịch hiện đại có thể cảnh báo rằng modifier này không còn cần thiết.

Bài học thuộc phần **Phép toán dấu phẩy động** của module **Java core – numbers**. Trọng tâm là hiểu “strict” nghĩa là gì, vì sao từng có `strictfp`, điều gì thực sự thay đổi trong Java 17, và những điều **always-strict không bảo đảm**.

## 1. “Strict floating-point” thực sự có nghĩa gì?

Java sử dụng biểu diễn số dấu phẩy động nhị phân IEEE 754:

| Kiểu | Định dạng nhị phân | Độ chính xác phần trị | Số mũ và miền giá trị |
| --- | --- | --- | --- |
| `float` | binary32, 32 bit | 24 bit kể cả bit ẩn | Miền tương ứng với binary32 |
| `double` | binary64, 64 bit | 53 bit kể cả bit ẩn | Miền tương ứng với binary64 |

Khi đánh giá **strict**, mỗi biểu thức có kiểu `float` chỉ nhận giá trị biểu diễn được bằng `float` chuẩn; mỗi biểu thức có kiểu `double` chỉ nhận giá trị biểu diễn được bằng `double` chuẩn. Các phép toán tương ứng với IEEE 754 tạo kết quả theo định dạng và quy tắc làm tròn được đặc tả, không được âm thầm duy trì một tập giá trị trung gian có số mũ lớn hơn kiểu của biểu thức.

Ví dụ, với `double`:

```java
double x = Double.MAX_VALUE;
double result = (x * 2.0) / 2.0;
// result là Infinity, không trở về x.
```

Tại bước `x * 2.0`, giá trị toán học vượt miền **hữu hạn** của `double`, nên kết quả là `+Infinity`. Sau đó `Infinity / 2.0` vẫn là `Infinity`.

Đây là ví dụ minh họa sự khác nhau giữa toán học số thực lý tưởng và đánh giá dấu phẩy động với miền số mũ hữu hạn. Không được diễn giải `(x * 2) / 2 == x` là một đẳng thức luôn đúng khi dùng `double`.

**Strict không có nghĩa vô hạn độ chính xác.** Kết quả hữu hạn vẫn có thể bị làm tròn; `0.1` và `0.2` không có biểu diễn nhị phân hữu hạn chính xác; phép toán có thể tràn thành vô cực hoặc underflow thành số subnormal/zero có dấu. Strict chỉ khiến **quy tắc đánh giá được xác định chặt chẽ**, không biến `float`/`double` thành `BigDecimal`.

## 2. Lược sử ba giai đoạn của dấu phẩy động Java

| Giai đoạn | Hành vi mặc định | Vai trò của `strictfp` |
| --- | --- | --- |
| Java 1.0–1.1 | Luôn dùng ngữ nghĩa strict | Chưa có sự phân đôi chế độ như Java 1.2 |
| Java 1.2–16 | Có thể dùng strict hoặc chế độ cho phép tập giá trị trung gian với **số mũ mở rộng** ở những nơi đặc tả cho phép | Yêu cầu đánh giá strict trong phạm vi được khai báo |
| **Java 17 trở lên** | **Mọi biểu thức `float`/`double` đều always-strict** | Giữ để tương thích mã cũ; không còn ảnh hưởng phép tính |

### 2.1. Giai đoạn Java 1.0 và 1.1

Những phiên bản đầu Java đã yêu cầu phép toán dấu phẩy động có ngữ nghĩa strict. Điều này phục vụ mục tiêu chương trình có hành vi được quy định rõ ràng trên các môi trường thực thi khác nhau.

### 2.2. Từ Java 1.2 đến Java 16: lý do xuất hiện strictfp

Một số họ CPU đời cũ có đặc điểm phần cứng khiến việc thực hiện chính xác chế độ strict tốn chi phí đáng kể. Vì thế, từ Java 1.2, đặc tả cho phép một số phép tính `float` hoặc `double` **không FP-strict** dùng tập giá trị **extended-exponent**:

- `float-extended-exponent value set`: **cùng số bit chính xác phần trị** như `float`, nhưng miền số mũ được mở rộng.
- `double-extended-exponent value set`: **cùng số bit chính xác phần trị** như `double`, nhưng miền số mũ được mở rộng.

Điểm dễ nhầm: các tập giá trị lịch sử này được mô tả với **miền số mũ lớn hơn**, **không phải bảo đảm có thêm bit chính xác phần trị**. Không nên tóm tắt sai rằng “không strict thì Java được phép giữ toàn bộ phép tính ở bất kỳ độ chính xác 80-bit nào”.

Với phép tính không strict, khi phần cứng/JVM được phép sử dụng miền số mũ mở rộng, một kết quả trung gian có thể tránh tràn hoặc underflow ở một vị trí mà phép tính strict đã đạt vô cực hoặc zero. Điều đó có thể tạo khác biệt ở kết quả cuối trong các môi trường lịch sử.

`strictfp` được đưa vào để lập trình viên **chủ động yêu cầu strict evaluation** ở class/interface hoặc method thích hợp, khống chế khác biệt cho những biểu thức nằm trong phạm vi áp dụng.

### 2.3. Từ Java 17: JEP 306 khôi phục always-strict

Phần cứng và khả năng triển khai JVM đã tiến bộ, làm cho sự linh hoạt vì phần cứng cũ không còn cần thiết. **JEP 306** thống nhất lại ngữ nghĩa:

- Không còn cho phép phép toán dấu phẩy động Java sử dụng tập giá trị trung gian có miền số mũ mở rộng thay cho `float`/`double` chuẩn.
- Mọi biểu thức dấu phẩy động Java được đánh giá strict, **dù có hoặc không có `strictfp`**.
- Từ khóa `strictfp` được giữ vì tương thích mã nguồn, nhưng không tạo “chế độ nghiêm ngặt hơn” cho phương thức/class có đánh dấu.

Đây là thay đổi ở **đặc tả ngôn ngữ và máy ảo**, không chỉ là lựa chọn trình biên dịch hay một cờ tối ưu của riêng HotSpot.

## 3. Cách dùng strictfp trong mã Java cũ

Trong các phiên bản mà `strictfp` có tác dụng, modifier này thường được đặt trên **class**, **interface** hoặc **method** thích hợp để các biểu thức dấu phẩy động trong phạm vi đó có ngữ nghĩa strict.

Ví dụ cú pháp:

```java
public strictfp class LegacyCalculator {
    public double calculate(double x, double y) {
        return (x * y) / 3.0;
    }
}
```

Hoặc:

```java
public class LegacyCalculator {
    public static strictfp double calculate(double x, double y) {
        return (x * y) / 3.0;
    }
}
```

Hai đoạn trên là **mẫu khai báo độc lập**, không nên đặt cả hai class `public` cùng tên trong một tệp. Trong Java 17+, modifier vẫn hợp lệ về cú pháp nhưng **không thay đổi ngữ nghĩa đánh giá**. Với mã Java 17+ viết mới, thông thường không cần thêm `strictfp` chỉ để có kết quả strict.

Không phải mọi vị trí trong Java đều nhận modifier `strictfp`; chẳng hạn, nó không phải modifier dành cho một biến số riêng lẻ. Trong code review mã cũ, cần đọc phiên bản Java mục tiêu để hiểu nguyên nhân lịch sử của modifier.

## 4. Ví dụ sự khác biệt về số mũ trung gian

Xét phép tính:

```java
double x = Double.MAX_VALUE;
double value = x * 2.0 / 2.0;
```

Trong đánh giá **strict**, kết quả của `x * 2.0` là `Infinity`. Vì vậy kết quả cuối vẫn là `Infinity`, dù trong toán học số thực lý tưởng `(x × 2) ÷ 2 = x`.

Trong mô hình lịch sử cho phép **extended-exponent**, một số trường hợp có thể giữ trung gian có số mũ lớn hơn, khiến phần nhân chưa tràn ngay trong giá trị trung gian. Khi các bước tiếp theo đưa giá trị trở về miền chuẩn, kết quả có thể khác.

Lưu ý ba giới hạn khi dùng ví dụ này:

1. Nó mô tả **lý do có thể khác** giữa các chế độ đánh giá lịch sử, **không khẳng định** rằng mọi JVM trước Java 17 chắc chắn trả một giá trị khác.
2. Các đoạn mã không strict ở Java 1.2–16 vẫn có thể được đánh giá strict trong nhiều môi trường. Việc cho phép miền số mũ mở rộng không bắt buộc JVM phải dùng miền đó.
3. Trong **Java 17+**, không cần và không thể dùng `strictfp` để thay đổi lựa chọn giữa hai chế độ này: **chỉ có ngữ nghĩa strict**.

Bởi vậy, khi phân tích một lỗi số học ghi nhận trên JVM cũ, hãy xem cả **phiên bản Java**, CPU/JVM và nguồn code có `strictfp`; đừng áp dụng suy luận “strictfp thay đổi kết quả” cho một chương trình thuần Java 17+ hiện đại.

## 5. Strict khác gì với độ chính xác số học?

Ngay cả khi luôn strict:

```java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3); // false
```

`0.1` và `0.2` không thể được biểu diễn chính xác bằng số hữu hạn bit của binary64. Mỗi phép toán làm tròn theo quy tắc IEEE 754 phù hợp. Strict yêu cầu phép toán tạo ra **kết quả đã làm tròn có thể biểu diễn**, không yêu cầu kết quả bằng số thực toán học vô hạn độ chính xác.

### Các điểm không thay đổi bởi always-strict

- `float` vẫn có khoảng 24 bit độ chính xác nhị phân; `double` vẫn có khoảng 53 bit.
- `NaN`, `+Infinity`, `-Infinity`, `+0.0`, `-0.0` vẫn tồn tại và hoạt động theo quy tắc số thực của Java.
- Phép chia dấu phẩy động cho zero vẫn có thể tạo vô cực/NaN thay vì `ArithmeticException`.
- Kết quả phép cộng, nhân có thể thay đổi khi đổi **thứ tự tính toán** do làm tròn và tràn.
- Không nên dùng `double` thay `BigDecimal` cho tiền hoặc nghiệp vụ đòi thập phân chính xác chỉ vì Java 17 đã always-strict.

### Strict và thứ tự đánh giá biểu thức

```java
double big = 1e16;

double left = (big + 1.0) - big; // 0.0
double right = (big - big) + 1.0; // 1.0
```

Ở miền `1e16`, chênh lệch 1 quá nhỏ để `double` phân biệt sau phép cộng với `big`, nên `(big + 1.0)` được làm tròn trở lại `big`. Nhưng `big - big` cho 0 chính xác, rồi cộng 1 cho 1.0.

**Always-strict không làm phép cộng dấu phẩy động có tính kết hợp như số thực toán học.** Nó chỉ xác định kết quả tương ứng với biểu thức và thứ tự đánh giá mà Java đã quy định. Đổi nhóm bằng dấu ngoặc, đổi thứ tự cộng dồn hoặc thay thuật toán vẫn có thể đổi kết quả.

## 6. Strict không có nghĩa “bất kể thao tác nào cũng cho cùng bit”

Từ Java 17, các toán tử dấu phẩy động của Java và các phép chuyển đổi tương ứng có quy tắc đánh giá strict. Nhưng nếu hai chương trình **không cùng phép toán hoặc không cùng thuật toán**, chúng không buộc phải cho cùng kết quả bit.

### 6.1. Math.fma khác với nhân rồi cộng riêng

`Math.fma(a, b, c)` (*fused multiply-add*) thực hiện tích và tổng với **một lần làm tròn cuối**, thay vì làm tròn sau nhân rồi lại làm tròn sau cộng. Nó có thể cho kết quả khác so với `a * b + c` ngay trên Java 17+:

```java
double epsilon = Math.ulp(1.0);
double a = 1.0 + epsilon;
double b = 1.0 - epsilon;

double separate = a * b - 1.0;
double fused = Math.fma(a, b, -1.0);

System.out.println(separate == 0.0); // true
System.out.println(fused < 0.0);      // true
```

Vì tích chính xác của hai toán hạng là `1 - epsilon²`, phép nhân riêng làm tròn về 1.0 rồi phép trừ cho 0.0. `fma` chỉ làm tròn một lần sau tổng cuối và giữ được phần dư âm rất nhỏ.

**Sự khác biệt này không phải lỗi vi phạm always-strict.** `Math.fma` là một phép toán khác, có quy tắc rõ ràng. Một tối ưu hóa không được tự ý thay `a*b+c` bằng `Math.fma(a,b,c)` nếu thay đổi kết quả có thể quan sát được.

### 6.2. Math và StrictMath không phải strictfp

Tên `StrictMath` dễ gây nhầm với modifier `strictfp`.

- **`strictfp`** là modifier ngôn ngữ lịch sử, liên quan đến cách đánh giá **biểu thức** trong phạm vi áp dụng.
- **`Math`** là lớp thư viện toán học có các hàm `sin`, `cos`, `log`, `sqrt`, `fma`, v.v. Hợp đồng làm tròn và sai số phụ thuộc **từng phương thức**.
- **`StrictMath`** là lớp thư viện được thiết kế cho các yêu cầu tái lập kết quả của những hàm được đặc tả theo cách nghiêm ngặt, đặc biệt nhiều hàm siêu việt gắn với thuật toán chuẩn tham chiếu lịch sử.

Java 17 always-strict **không có nghĩa mọi lời gọi `Math.sin` và `StrictMath.sin` đều phải có bit giống nhau** trong mọi tình huống. Cần đọc hợp đồng phương thức cụ thể, nhất là khi thuật toán yêu cầu tái lập bit giữa môi trường khác nhau.

Cũng không nên mặc định rằng thay mọi lời gọi `Math` bằng `StrictMath` là cần thiết hoặc giúp xử lý mọi sai số; nó giải quyết một lớp yêu cầu về thư viện toán học, không thay thế thiết kế thuật toán hay lựa chọn kiểu số.

### 6.3. Song song và thứ tự cộng dồn

Hai luồng tính tổng cùng dữ liệu nhưng theo hai thứ tự khác nhau có thể nhận kết quả dấu phẩy động khác nhau. Always-strict không buộc `parallelStream().sum()` và một vòng lặp tuần tự phải đánh giá các phép cộng theo đúng cùng cây tính toán nếu API cho phép khác biệt thuật toán.

Khi cần tái lập kết quả, hãy kiểm soát **thứ tự phép toán**, cách chia nhóm, thuật toán cộng dồn và những lời gọi thư viện liên quan. `strictfp` trên Java 17 không giải quyết thay cho những quyết định này.

## 7. Java 17+ xử lý overflow, underflow, NaN và signed zero thế nào?

Strict evaluation vẫn bao gồm các giá trị IEEE 754 đặc biệt:

| Biểu thức | Kết quả ở Java 17+ | Điều cần hiểu |
| --- | --- | --- |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Tràn miền hữu hạn của double |
| `Double.MIN_VALUE / 2.0` | `+0.0` | Underflow từ số dương subnormal nhỏ nhất |
| `-Double.MIN_VALUE / 2.0` | `-0.0` | Underflow giữ dấu |
| `1.0 / 0.0` | `Infinity` | Chia thực cho 0 không ném ArithmeticException |
| `0.0 / 0.0` | `NaN` | Phép toán không có kết quả số thực xác định |
| `0.1 + 0.2 == 0.3` | `false` | Dấu phẩy động nhị phân vẫn làm tròn |
| `Math.fma(a,b,c)` so với `a*b+c` | Có thể khác nhau | Khác số lần làm tròn |

`Double.MIN_VALUE` **không phải số double âm nhỏ nhất**; nó là số dương khác 0 nhỏ nhất của `double`. Đây là một ca kiểm thử underflow rất hữu ích.

Với giá trị rất nhỏ nhưng vẫn biểu diễn được, Java hỗ trợ **subnormal numbers** và **gradual underflow**, không được tự ý “flush to zero” mọi số dưới ngưỡng chuẩn hóa. Trong Java 17+, các quy tắc strict cho `float`/`double` tiếp tục áp dụng ở những miền này.

## 8. Compiler xử lý strictfp trên Java 17+ ra sao?

Một chương trình Java 17+ vẫn có thể khai báo:

```java
public class LegacyStrictDemo {
    public static strictfp double twice(double x) {
        return x * 2.0;
    }
}
```

Đây là đoạn source độc lập và tên file phải là `LegacyStrictDemo.java`. Với `javac` hiện đại, khai báo có thể gây cảnh báo dạng:

```text
[strictfp] as of release 17, all floating-point expressions
are evaluated strictly and 'strictfp' is not required
```

Thông báo cụ thể/phần đường dẫn/số dòng phụ thuộc phiên bản công cụ, nên không nên coi chuỗi cảnh báo này là **stdout của chương trình**. Nó là cảnh báo **lúc biên dịch**, không phải kết quả của toán tử dấu phẩy động.

### Có nên xóa strictfp khỏi code cũ?

Nếu **chỉ triển khai và biên dịch cho Java 17 trở lên**, thường có thể bỏ modifier dư thừa mà không làm thay đổi ngữ nghĩa phép toán `float`/`double`. Tuy nhiên:

1. Hãy xác nhận phạm vi build thực sự chỉ nhắm Java 17+.
2. Nếu cùng source vẫn cần tương thích với Java 8/11 hay các phiên bản trước 17, không vội xóa `strictfp` khi tính tái lập dấu phẩy động có thể phụ thuộc modifier đó.
3. Kiểm thử những thuật toán nhạy với dấu phẩy động trước và sau refactor, đặc biệt nếu đồng thời thay đổi thứ tự phép toán, hàm `Math`/`StrictMath` hoặc phương thức `fma`.
4. Không cần thêm `strictfp` để “vá” sai số `0.1 + 0.2` hoặc để ép chương trình tự ném exception khi tính vô cực.

Cách giải thích phù hợp trong code review hiện đại là: **modifier còn được chấp nhận vì tương thích nhưng không làm kết quả phép tính strict hơn trên Java 17+**.

## 9. Chương trình Java 17+ chạy độc lập

Lưu file **`AlwaysStrictDemo.java`**:

```java
public class AlwaysStrictDemo {
    static double ordinary(double x) {
        return x * 2.0 / 2.0;
    }

    static strictfp double legacyStrict(double x) {
        return x * 2.0 / 2.0;
    }

    public static void main(String[] args) {
        double large = Double.MAX_VALUE;

        double plain = ordinary(large);
        double marked = legacyStrict(large);

        System.out.println("plain-infinite=" +
                Double.isInfinite(plain));
        System.out.println("marked-infinite=" +
                Double.isInfinite(marked));
        System.out.println("same-bits=" +
                (Double.doubleToLongBits(plain)
                        == Double.doubleToLongBits(marked)));

        double big = 1e16;
        System.out.println("round-left=" + ((big + 1.0) - big));
        System.out.println("round-right=" + ((big - big) + 1.0));
        System.out.println("decimal-equal=" + (0.1 + 0.2 == 0.3));

        double epsilon = Math.ulp(1.0);
        double a = 1.0 + epsilon;
        double b = 1.0 - epsilon;
        double separate = a * b - 1.0;
        double fused = Math.fma(a, b, -1.0);

        System.out.println("separate-zero=" + (separate == 0.0));
        System.out.println("fused-negative=" + (fused < 0.0));

        System.out.println("positive-underflow=" +
                (Double.MIN_VALUE / 2.0));
        System.out.println("negative-underflow=" +
                (-Double.MIN_VALUE / 2.0));
        System.out.println("nan-check=" +
                Double.isNaN(0.0 / 0.0));
    }
}
```

Biên dịch/chạy trên JDK 17 hoặc mới hơn:

```bash
javac AlwaysStrictDemo.java
java AlwaysStrictDemo
```

**Lưu ý:** `javac` có thể phát cảnh báo `strictfp` không cần thiết. Cảnh báo đó là output biên dịch, **không nằm trong stdout dưới đây**.

Stdout của chương trình:

```text
plain-infinite=true
marked-infinite=true
same-bits=true
round-left=0.0
round-right=1.0
decimal-equal=false
separate-zero=true
fused-negative=true
positive-underflow=0.0
negative-underflow=-0.0
nan-check=true
```

Diễn giải:

- Hai phương thức có và không có `strictfp` cho cùng kết quả tại phép tính tràn `double` trên Java 17+: `Infinity`.
- `round-left` và `round-right` cho kết quả khác nhau vì **dấu ngoặc thay đổi thứ tự các phép toán**, không liên quan đến modifier.
- `decimal-equal=false` chứng minh always-strict **không loại bỏ sai số nhị phân**.
- `separate-zero=true` và `fused-negative=true` cho thấy phép `Math.fma` (một lần làm tròn) không tương đương nhân rồi trừ với hai lần làm tròn.
- Underflow có thể cho zero dương hoặc âm; NaN vẫn có thể xuất hiện từ `0.0/0.0`.

Không nên đưa một đoạn ví dụ chỉ chạy được trên Java 17+ rồi suy ra rằng JVM cũ **chắc chắn** trả kết quả khác ở chỗ không có `strictfp`. Các JVM cũ vẫn có thể lựa chọn strict evaluation ở những nơi đặc tả lịch sử cho phép.

## 10. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Java 17 bỏ từ khóa `strictfp` khỏi cú pháp.” | Modifier vẫn được nhận để tương thích, nhưng không ảnh hưởng đánh giá dấu phẩy động. |
| “Thêm `strictfp` vào Java 17 giúp kết quả chính xác hơn.” | Mọi biểu thức đã strict; modifier không bổ sung bit chính xác. |
| “Strictfp từng bảo đảm mọi tính toán ở độ chính xác thực vô hạn.” | Nó chỉ kiểm soát tập giá trị `float`/`double` và phép làm tròn phù hợp; kết quả vẫn có sai số. |
| “Chế độ không strict lịch sử luôn dùng phần trị nhiều bit hơn.” | Cơ chế lịch sử được đặc tả qua **extended exponent** với cùng số bit phần trị, không phải quyền tùy ý tăng precision. |
| “Mọi JVM trước 17 đều cho kết quả khác khi bỏ strictfp.” | Chế độ số mũ mở rộng được **cho phép**, không bị bắt buộc ở mọi JVM. |
| “Always-strict khiến phép cộng double có tính kết hợp.” | `(a+b)+c` vẫn có thể khác `a+(b+c)` do làm tròn. |
| “Always-strict khiến `Math.fma(a,b,c)` giống `a*b+c`.” | `fma` có một lần làm tròn, biểu thức tách rời có thể hai lần. |
| “`strictfp` và `StrictMath` là một tính năng.” | Modifier ngôn ngữ và lớp thư viện là hai cơ chế riêng. |
| “Strict có nghĩa mọi `Math`/ `StrictMath` bitwise giống nhau.” | Cần xem hợp đồng và thuật toán từng phương thức. |
| “Always-strict giúp tính tiền bằng double chính xác thập phân.” | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất vẫn phù hợp hơn khi yêu cầu decimal exactness. |
| “Một cảnh báo strictfp lúc biên dịch là lỗi runtime.” | Đó là warning từ compiler; chương trình vẫn có thể chạy. |

## 11. Áp dụng trong ứng dụng và kiểm thử

### 11.1. Khi nâng phiên bản Java

Một dự án cũ chuyển từ Java 8/11 sang Java 17 nên:

- Kiểm tra những chỗ dùng `strictfp` và ghi chú lý do lịch sử, nếu có.
- Đối chiếu kết quả ở các thuật toán nhạy với overflow/underflow, số subnormal, phép tính lặp nhiều lần và điều kiện ngưỡng.
- Không quy kết mọi thay đổi số học khi nâng Java cho JEP 306: thay đổi thư viện, thuật toán, thứ tự tổng hợp, kiểu dữ liệu hoặc mã ứng dụng cũng có thể làm khác kết quả.
- Nếu mã dùng `Math.sin`, `Math.log`… và cần khả năng lặp lại kết quả có tính ràng buộc, kiểm tra hợp đồng API cụ thể thay vì chỉ thêm modifier.

### 11.2. Khi thiết kế code Java 17+ mới

Lựa chọn thông thường là **không dùng `strictfp`**. Tập trung vào:

1. Chọn đúng kiểu `float`, `double`, `BigDecimal` hay số nguyên theo ý nghĩa dữ liệu.
2. Xác định mức sai số có thể chấp nhận và quy tắc so sánh.
3. Xác thực `NaN` và vô cực bằng `Double.isFinite` hoặc `Float.isFinite` nếu miền yêu cầu hữu hạn.
4. Kiểm soát thứ tự phép toán, phép cộng dồn song song và các lời gọi như `Math.fma`.
5. Kiểm thử biên gần overflow, subnormal và zero có dấu khi thuật toán nhạy với chúng.

### 11.3. Khi phải tái lập bit giữa nhiều máy hoặc nhiều lần chạy

Always-strict giúp **thu hẹp nguồn khác biệt từng đến từ các chế độ số mũ trung gian**. Nhưng một lời hứa “kết quả bit-for-bit giống nhau” cho cả ứng dụng còn phụ thuộc vào:

- Có dùng cùng biểu thức và cùng dữ liệu đầu vào bit-for-bit hay không.
- Thứ tự tính toán và các lần làm tròn (ví dụ FMA so với nhân/cộng riêng).
- Việc gọi các hàm thư viện có bảo đảm kết quả xác định theo hợp đồng cụ thể hay không.
- Mô hình song song, thứ tự reduction và những thay đổi của thuật toán.

Một phép toán primitive được xác định chặt chẽ **không tự làm toàn bộ pipeline số học trở thành có tính quyết định** nếu pipeline còn những lựa chọn thuật toán khác nhau.

## 12. Câu hỏi tự kiểm tra

1. Tại sao Java 17 gọi là **always-strict**, và nó khác gì chế độ mặc định cho phép extended exponent trên Java 1.2–16?
2. `strictfp` lịch sử mở rộng số bit phần trị hay chỉ **hạn chế sự mở rộng miền số mũ trung gian**? Giải thích đúng bản chất.
3. Trên Java 17+, hai phương thức có và không có `strictfp` nhưng có cùng biểu thức `double` có cần hai chế độ tính toán riêng không? Vì sao compiler có thể cảnh báo?
4. Vì sao `Double.MAX_VALUE * 2.0 / 2.0` không trả lại `Double.MAX_VALUE` trong ngữ nghĩa strict?
5. Vì sao `(1e16 + 1.0) - 1e16` khác `(1e16 - 1e16) + 1.0`? Always-strict có thay đổi điều đó không?
6. Hãy giải thích sự khác nhau giữa `Math.fma(a,b,c)` và `a*b+c` về **số lần làm tròn**.
7. Có nên thay toàn bộ `Math` bằng `StrictMath` để “bật strictfp” trong Java 17? Nêu đúng vai trò của từng tên.
8. Một ứng dụng Java 8 có `strictfp` trên các phép tính nhạy với số mũ. Khi nâng lên Java 17 và muốn xóa modifier, bạn cần kiểm tra những gì?
9. Vì sao always-strict không khiến `0.1 + 0.2 == 0.3` thành `true`?
10. Nếu ứng dụng Java 17 tính tổng theo nhiều thứ tự trong các worker khác nhau, sự khác biệt kết quả có thể xuất hiện dù mọi biểu thức đều strict không?

## 13. Checklist ghi nhớ

- **Java 17+ luôn strict:** không còn chọn giữa hai chế độ đánh giá dấu phẩy động theo `strictfp`.
- **`strictfp` mang tính lịch sử và tương thích nguồn** trên Java 17+; không mang đến độ chính xác cao hơn.
- **Java 1.2–16 cho phép extended-exponent value sets** trong ngữ cảnh không strict; cùng độ chính xác phần trị, miền số mũ rộng hơn.
- **Strict không loại bỏ làm tròn**, overflow, underflow, signed zero, Infinity hoặc NaN.
- **Biểu thức và thứ tự phép toán vẫn quan trọng**; `Math.fma` khác phép nhân cộng tách rời.
- **`StrictMath` là API thư viện**, không phải cơ chế kích hoạt modifier `strictfp`.
- **Kiểm thử reproducibility ở mức toàn thuật toán**, không chỉ nhìn modifier ở một method.
- Với dữ liệu cần **thập phân chính xác**, vẫn phải dùng mô hình số thích hợp như `BigDecimal`, không trông cậy `strictfp`.

### Nguồn đặc tả để đọc thêm

- [JEP 306 – Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).
- [Java Language Specification, Java SE 17 – §15.4 Floating-point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4).
- [Java Virtual Machine Specification, Java SE 17 – §2.8 Floating-Point Arithmetic](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.8).

**Kết luận:** Java 17 không “làm số thực trở nên chính xác tuyệt đối”, mà **loại bỏ sự khác biệt về chế độ đánh giá strict/non-strict từng được cho phép vì phần cứng cũ**. `strictfp` vẫn xuất hiện trong mã di sản nhưng không làm thay đổi kết quả biểu thức Java 17+. Khi đánh giá tính đúng của phép toán thực, hãy chú ý miền biểu diễn, làm tròn, thứ tự phép tính, API thư viện và thuật toán.
