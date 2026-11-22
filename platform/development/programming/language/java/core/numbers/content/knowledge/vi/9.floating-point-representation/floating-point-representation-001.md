# `float` theo binary32 và `double` theo binary64 trong Java

`float` và `double` đều là kiểu nguyên thủy để làm việc với số dấu phẩy động nhị phân trong Java. `float` dùng **IEEE 754 binary32 (32 bit)**, còn `double` dùng **IEEE 754 binary64 (64 bit)**. Điểm khác biệt cần nắm đầu tiên là **độ phân giải và miền độ lớn có thể biểu diễn**, chứ không phải một số lượng cố định chữ số sau dấu chấm thập phân.

Bài này tập trung vào **so sánh hai định dạng và ra quyết định chọn kiểu**. Các bài tiếp theo giải mã bit, phân tích precision, underflow, giá trị đặc biệt và API chuyển bit ở chiều sâu riêng.

## 1. Bảng so sánh binary32 và binary64

| Thuộc tính | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Tổng độ rộng | 32 bit | 64 bit |
| Bit dấu | 1 | 1 |
| Trường exponent lưu | 8 bit | 11 bit |
| Trường fraction lưu | 23 bit | 52 bit |
| Significand của số normal, kể cả bit 1 ẩn | 24 bit | 53 bit |
| Exponent bias | 127 | 1023 |
| Exponent thật ở miền normal | −126 đến +127 | −1022 đến +1023 |
| Chữ số thập phân có nghĩa thường dùng làm ước lượng | Khoảng 6–7 | Khoảng 15–16 |
| Số normal dương nhỏ nhất | `Float.MIN_NORMAL = 2^-126` | `Double.MIN_NORMAL = 2^-1022` |
| Số dương khác zero nhỏ nhất | `Float.MIN_VALUE = 2^-149` | `Double.MIN_VALUE = 2^-1074` |
| Số hữu hạn dương lớn nhất | `Float.MAX_VALUE ≈ 3.4 × 10^38` | `Double.MAX_VALUE ≈ 1.8 × 10^308` |

Trong số **normal**, một bit 1 dẫn đầu phần trị được ngầm hiểu. Vì thế trường fraction 23/52 bit đem lại **24/53 bit precision** tương ứng. Với số **subnormal** rất gần zero, bit dẫn này không có; độ chính xác tương đối giảm dần. `MIN_VALUE` của hai wrapper dấu phẩy động là **số dương khác 0 nhỏ nhất**, không phải số âm hữu hạn nhỏ nhất; số âm hữu hạn có trị tuyệt đối lớn nhất là `-MAX_VALUE`.

### Miền lớn không đồng nghĩa chính xác từng đơn vị

Phần **exponent** cho phép biến thiên rộng về độ lớn. Phần **significand** giới hạn chi tiết giữa các số ở cùng độ lớn. Chẳng hạn binary32 có thể chứa số hữu hạn khoảng `10^38`, nhưng ở quanh `2^24` đã không còn phân biệt được tất cả số nguyên kề nhau. Tương tự, binary64 không phân biệt liên tiếp mọi số nguyên sau `2^53`.

Nhờ nhiều bit exponent và fraction hơn, binary64 biểu diễn được các số có độ lớn rộng hơn và thường gần giá trị toán học hơn binary32. Tuy nhiên, không kiểu nào có thể lưu chính xác **mọi phân số thập phân**.

## 2. Quan sát cùng giá trị đầu vào ở hai định dạng

Trong Java, literal `0.1` mặc định là `double`; hậu tố `f` tạo literal `float`:

```java
float lowPrecision = 0.1f;
double highPrecision = 0.1;
double widened = lowPrecision;

System.out.println(lowPrecision);            // 0.1
System.out.println(highPrecision);           // 0.1
System.out.println(widened);                 // 0.10000000149011612
System.out.println(Float.toHexString(lowPrecision));
// 0x1.99999ap-4
System.out.println(Double.toHexString(highPrecision));
// 0x1.999999999999ap-4
```

`1/10` có khai triển nhị phân vô hạn, nên mỗi định dạng lưu số gần nhất theo độ chính xác của mình. Hai lời gọi `println` đầu cùng in `0.1` vì Java chọn chuỗi có thể đọc ngược về **giá trị đã lưu ở từng kiểu**. Khi `float` được mở rộng thành `double`, Java giữ đúng **giá trị binary32 đã làm tròn**; phép widening không tái tạo phân số 1/10 ban đầu.

Muốn xem mã hóa thay vì chuỗi số thập phân, dùng bit API:

```java
System.out.printf("0x%08x%n", Float.floatToRawIntBits(0.1f));
// 0x3dcccccd
System.out.printf("0x%016x%n", Double.doubleToRawLongBits(0.1));
// 0x3fb999999999999a
```

Đây là **hai mẫu bit IEEE 754**, không phải hai số nguyên được tạo bằng cast số học. Bài về sign/exponent/fraction sẽ chỉ cách giải mã từng trường; hai bài cuối chương sẽ phân biệt `raw`/canonical NaN và cách dựng lại số từ bit pattern.

## 3. Chọn định dạng theo yêu cầu dữ liệu

| Tình huống | Kiểu/cách biểu diễn thường phù hợp | Điều kiện quyết định |
| --- | --- | --- |
| Tính toán khoa học hoặc nghiệp vụ chấp nhận xấp xỉ nhị phân | `double` | Cần precision rộng hơn và đủ miền; vẫn đánh giá sai số số học |
| Buffer ảnh, dữ liệu đồ họa hoặc cảm biến bắt buộc 32 bit | `float` | Hợp đồng lưu/truyền binary32 và sai số ở các miền giá trị thực tế đều đạt |
| Mảng primitive rất lớn, nhạy với bộ nhớ và băng thông | `float[]` nếu đủ precision | Mỗi phần tử primitive 4 byte thay vì 8 byte; xét cả overhead cấu trúc |
| Số đếm, ID, offset cần chính xác từng đơn vị | `int`, `long` hoặc `BigInteger` | Không để làm tròn chấm động gộp hai giá trị nguyên khác nhau |
| Tiền, thuế, thập phân theo số chữ số cố định | `BigDecimal` từ chuỗi hoặc số nguyên đơn vị nhỏ nhất | Xác định scale, rounding và miền số chính xác ngay từ đầu |
| Giao thức nhị phân phải giữ mọi bit, kể cả payload NaN | `int`, `long`, `byte[]` ở lớp truyền tải | Chốt độ rộng, byte order và yêu cầu bit-exact trước khi tính toán |

**`double` là lựa chọn mặc định hợp lý cho nhiều phép tính số thực Java**, nhưng không tự động là lựa chọn tốt nhất khi API ngoài bắt buộc binary32 hay khi biểu diễn số thập phân phải chính xác. Chọn `float` vì dung lượng chỉ hợp lý sau khi kiểm tra sai số ở **giá trị lớn, nhỏ, gần 0 và sau nhiều bước tính**, không phải vì hai biến đều hiển thị giống nhau.

### Kiểm tra giới hạn khi đổi kiểu

Chuyển `double` sang `float` là narrowing; một giá trị còn hữu hạn ở binary64 có thể thành Infinity ở binary32:

```java
double large = 1e40;
float narrowed = (float) large;
System.out.println(narrowed);            // Infinity
System.out.println(Float.isFinite(narrowed)); // false
```

Tương tự, số rất nhỏ có thể biến thành `float` subnormal hoặc zero. Ngược lại, chuyển `float` sang `double` giữ đúng giá trị số đã lưu trong `float`, nhưng **không** khôi phục thông tin bị mất trong chuyển đổi trước đó.

Khi dữ liệu phải hữu hạn, hãy kiểm tra `Float.isFinite`/`Double.isFinite` trên **kết quả sau chuyển kiểu** và ràng buộc miền theo nghiệp vụ. Các toán tử chấm động có thể tạo NaN hoặc Infinity mà không ném `ArithmeticException`, khác phép chia số nguyên cho zero.

## 4. Literal, biểu thức và điểm làm tròn

```java
double d = 1.25;  // literal mặc định double
float f = 1.25f;  // hậu tố f yêu cầu float
float explicitlyNarrowed = (float) d;
// float invalid = d;  // không tự chuyển double sang float
```

`float` và `double` có cùng nhóm phép toán nhưng **mỗi phép toán có thể làm tròn** theo độ chính xác của kiểu thực hiện. Nếu biểu thức trộn `float` với `double`, quy tắc promotion có thể đưa toán hạng `float` sang `double` trước phép toán, nhưng vẫn mang giá trị `float` đã được làm tròn. Trong Java 17+, ngữ nghĩa floating-point luôn strict theo JEP 306; điều này không biến tính toán thành số học thực tuyệt đối chính xác.

Một ví dụ chọn sai kiểu lưu số nguyên:

```java
int original = 16_777_217; // 2^24 + 1
float rounded = original;
System.out.println((int) rounded); // 16777216
System.out.println(Math.ulp(16_777_216f)); // 2.0
```

Do phần trị binary32 có 24 bit chính xác, số nguyên này bị làm tròn. `double` có ngưỡng tương tự tại `2^53`, không có nghĩa mọi số nguyên lớn hơn ngưỡng đều không biểu diễn được. Bài về **phạm vi số nguyên liên tiếp** sẽ phân tích đầu mút và những bẫy khi so sánh `long` với `double`.

### Một ngưỡng sai số không dùng chung cho mọi số

`Math.ulp(1f)` khoảng `1.19E-7`, còn `Math.ulp(1d)` khoảng `2.22E-16`. Ở số lớn hơn, bước biểu diễn thường lớn hơn. Ngưỡng so sánh gần bằng phải xuất phát từ dữ liệu và bài toán (có thể kết hợp sai số tuyệt đối/tương đối), đồng thời xử lý NaN, Infinity và signed zero. ULP mô tả lưới biểu diễn; **không phải** một bảo đảm sai số của mọi chuỗi phép toán.

## 5. Một chương trình so sánh có thể tự kiểm chứng

Lưu dưới tên `FloatingFormatsComparisonDemo.java`, chạy bằng Java 17+:

```java
public class FloatingFormatsComparisonDemo {
    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;

        System.out.println("float bits="
                + Integer.toHexString(Float.floatToRawIntBits(f)));
        System.out.println("double bits="
                + Long.toHexString(Double.doubleToRawLongBits(d)));
        System.out.println("float widened=" + (double) f);
        System.out.println("float precision bits=" + 24);
        System.out.println("double precision bits=" + 53);
        System.out.println("float ulp at one=" + Math.ulp(1.0f));
        System.out.println("double ulp at one=" + Math.ulp(1.0d));
        System.out.println("integer lost=" + (int) (float) 16_777_217);
        System.out.println("narrowed large=" + (float) 1e40);
        System.out.println("narrowed tiny=" + (float) 1e-50);
    }
}
```

```bash
javac --release 17 FloatingFormatsComparisonDemo.java
java FloatingFormatsComparisonDemo
```

Output (Java 17+):

```text
float bits=3dcccccd
double bits=3fb999999999999a
float widened=0.10000000149011612
float precision bits=24
double precision bits=53
float ulp at one=1.1920929E-7
double ulp at one=2.220446049250313E-16
integer lost=16777216
narrowed large=Infinity
narrowed tiny=0.0
```

Bốn phép thử dùng giá trị thập phân, bit pattern, ULP và chuyển kiểu để trả lời bốn câu hỏi khác nhau: đang lưu **mã nào**, khoảng lưới dày tới đâu, phép thu hẹp mất gì và giá trị còn hữu hạn hay không. Không suy tất cả từ một lần `println`.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `float` có 23 bit fraction lưu trữ nhưng 24 bit precision cho số normal? Sự khác biệt đó ảnh hưởng lựa chọn kiểu ra sao?
2. Tại sao `float f = 0.1f; double d = f;` không tương đương với `double d = 0.1;`?
3. Khi nào `float` là yêu cầu hợp đồng dữ liệu, và khi nào `double` cải thiện chất lượng phép tính?
4. Nếu cảm biến truyền `float` nhưng phép tính cần `double`, thông tin nào còn nguyên khi widening và thông tin nào không thể phục hồi?
5. Nếu một `double` phải dùng để lưu tiền chính xác theo cent, vấn đề là miền số, precision hay cơ số biểu diễn?
6. Làm sao xác nhận một bước narrowing từ `double` sang `float` vẫn thỏa yêu cầu về hữu hạn và sai số?

## 7. Liên hệ tới các bài chuyên sâu

- **Bit dấu, phần mũ và phần trị**: giải mã cụ thể cách 1/8/23 và 1/11/52 bit tạo giá trị.
- **Precision, 0.1, khoảng nguyên chính xác**: làm rõ sai số về độ phân giải, thập phân và chuyển số nguyên.
- **Normal/subnormal, ba hằng giới hạn, giá trị đặc biệt và ULP**: khảo sát các tình huống sát zero, tràn và khoảng cách giữa các số.
- **API đọc bit và dựng lại giá trị**: phục vụ debug, kiểm tra bit và trao đổi dữ liệu nhị phân đúng giao thức.

**Ghi nhớ:** sự khác nhau giữa binary32 và binary64 là một đánh đổi có thể kiểm chứng giữa **dung lượng, miền giá trị và độ phân giải**. Hãy chọn kiểu theo hợp đồng dữ liệu cùng sai số chấp nhận; chọn kiểu nguyên cho các đại lượng đếm cần đúng từng đơn vị và kiểu thập phân phù hợp cho nghiệp vụ cần decimal exact.