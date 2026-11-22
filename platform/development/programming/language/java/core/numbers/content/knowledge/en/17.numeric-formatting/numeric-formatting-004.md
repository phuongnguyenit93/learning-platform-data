# toHexString cho dấu phẩy động trong Java

Trong Java, **`Double.toHexString(double)`** và **`Float.toHexString(float)`** biểu diễn **giá trị dấu phẩy động** ở dạng **số thực hệ thập lục phân có số mũ cơ số 2**. Đây là cách hữu ích để quan sát chính xác những bit có nghĩa của một giá trị `float`/`double`, đặc biệt khi cần phân tích làm tròn, ULP, số subnormal và sự khác nhau giữa `0.1f` với `0.1d`.

```java
System.out.println(Double.toHexString(3.0));   // 0x1.8p1
System.out.println(Float.toHexString(1.0f));   // 0x1.0p0
System.out.println(Double.toHexString(0.1));   // 0x1.999999999999ap-4
```

Các lệnh trên là mảnh minh họa có thể đặt trong một phương thức Java. **Đừng nhầm `Double.toHexString` với `Integer.toHexString`**: hàm thứ nhất xuất ra **ký pháp số thực với dấu chấm và `p`**, còn hàm thứ hai xuất ra **chữ số hex của mẫu số nguyên**. `Double.toHexString` cũng **không phải** một phép lấy trực tiếp raw IEEE 754 bits hoặc chuỗi byte theo thứ tự endian.

## 1. Hai API và mục đích

| API | Đối số | Trả về | Ví dụ |
| --- | --- | --- | --- |
| `Double.toHexString(double d)` | Giá trị `double` 64 bit | `String` dạng hex floating-point | `Double.toHexString(1.0)` → `"0x1.0p0"` |
| `Float.toHexString(float f)` | Giá trị `float` 32 bit | `String` dạng hex floating-point | `Float.toHexString(1.0f)` → `"0x1.0p0"` |

Cả hai phương thức là **static**, dùng qua tên lớp `Double` hoặc `Float`. Không phải gọi trên đối tượng wrapper mới dùng được:

```java
double x = 3.0;
String formatted = Double.toHexString(x);  // "0x1.8p1"
```

Kết quả là **chuỗi để quan sát/ghi log/trao đổi dữ liệu dạng văn bản**, không làm thay đổi giá trị gốc. Phương thức không làm tròn thành một số chữ số thập phân theo locale; nó biểu diễn giá trị nhị phân đã lưu bằng ký pháp hex phù hợp.

Hình thức chuỗi dễ nhầm ở điểm: chữ số phần trị là **hex**, nhưng số mũ đứng sau `p` biểu thị **lũy thừa của 2**, không phải của 16 hay của 10. Dấu `p` là thành phần bắt buộc trong cú pháp hex floating-point được Java hỗ trợ.

## 2. Đọc chuỗi `0x1.8p1`

Một số hex floating-point hữu hạn normal có dạng đại ý:

```text
[-]0xH.FpE
    └─┬─┘ └┬┘
      │    └── E là số mũ viết bằng chữ số thập phân,
      │        nhưng chỉ lũy thừa của 2
      └─────── H.F là phần trị viết theo hệ 16
```

Đối với chuỗi `0x1.8p1`:

- `0x`: báo phần trị ở **cơ số 16**.
- `1.8`: phần trị = `1 + 8/16 = 1.5`.
- `p1`: nhân phần trị với `2^1 = 2`.
- Giá trị = `1.5 × 2 = 3.0`.

```text
0x1.8p1 = (1 + 8/16) × 2^1 = 3.0
0x1.0p0 = 1 × 2^0 = 1.0
0x1.0p-1 = 1 × 2^-1 = 0.5
0x1.0p3 = 1 × 2^3 = 8.0
0x1.fp3 = (1 + 15/16) × 2^3 = 15.5
```

Sau dấu chấm, **mỗi chữ số hex tương đương bốn bit nhị phân**, nên ký pháp rất thích hợp để xem một giá trị đã được biểu diễn sát các ngưỡng làm tròn hay chưa. Ví dụ `0x1.8` có phần `.8` tương đương `.1000` ở hệ nhị phân.

**Không đọc `p1` như `×10^1` hoặc `×16^1`**. Với các dấu phẩy động hex trong Java, `p` dùng số mũ cơ số 2; ký hiệu số mũ thập phân là `e` trong chuỗi thập phân như `1.5e2`.

## 3. Normal `double` và `float` được in khác nhau về số chữ số phần trị

Hai kiểu này đều theo biểu diễn nhị phân IEEE 754 nhưng có độ chính xác khác nhau:

| Thuộc tính | `float` | `double` |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit fraction được lưu | 23 | 52 |
| Bit significand hiệu dụng ở số normal | 24 | 53 |
| Số mũ không thiên lệch ở miền normal | -126 đến +127 | -1022 đến +1023 |
| ULP quanh `1.0` | `2^-23` | `2^-52` |

Vì một chữ số hex tương ứng bốn bit, phần fraction của `double` normal có thể cần tới **13 chữ số hex** để mô tả 52 bit. `float` normal cần nhiều nhất **6 chữ số hex** để mã hóa 23 bit fraction (bit thấp của chữ số cuối chứa phần đệm trong cách viết).

Ví dụ:

```java
System.out.println(Double.toHexString(0.1d));
// 0x1.999999999999ap-4

System.out.println(Float.toHexString(0.1f));
// 0x1.99999ap-4
```

Giá trị `0.1` trong thập phân không có biểu diễn nhị phân hữu hạn, nên hai kiểu làm tròn đến hai lưới biểu diễn khác nhau. Các chuỗi trên cho ta thấy rõ **các giá trị nhị phân lưu thực tế**; không phải hai cách “trang trí” khác nhau cho một giá trị chính xác `1/10`.

Các chữ số hex không phải một độ chính xác thập phân tùy chọn được ép theo số chữ số sau dấu chấm. `toHexString` tạo chuỗi xác định theo giá trị `float` hoặc `double` đã có, không tự tăng độ chính xác của biến.

## 4. Tại sao `0x1.0p0` không ghi đủ mọi chữ số 0 của fraction?

Java xuất **dạng ngắn gọn, có quy tắc**, thay vì luôn đệm đủ 6 hoặc 13 chữ số phần fraction.

```java
Double.toHexString(1.0);  // "0x1.0p0"
Double.toHexString(2.0);  // "0x1.0p1"
Double.toHexString(3.0);  // "0x1.8p1"
```

Ở `1.0`, fraction toàn zero, nên không cần ghi `0x1.0000000000000p0`. Java vẫn để **ít nhất một chữ số sau dấu chấm**, vì đây là định dạng của một số thực hex chứ không phải integer hex.

Trong miền số normal, chữ số đầu thường là `1` vì **significand chuẩn hóa** của số nhị phân có dạng `1.fraction`. Điều đó khác miền **subnormal**, nơi phần đầu được in `0.` và số mũ được giữ ở cận normal nhỏ nhất.

Lưu ý một giá trị có thể có **nhiều chuỗi toán học tương đương** trước khi chuẩn hóa, ví dụ `0x1.0p0` và `0x2.0p-1` cùng bằng 1. Hàm `toHexString` chọn định dạng được chuẩn hóa theo đặc tả API; không phải mọi chuỗi mà parser chấp nhận đều sẽ được in lại y nguyên.

## 5. Số normal: ví dụ biểu diễn các ngưỡng

Đối với `double`:

| Giá trị | `Double.toHexString` |
| --- | --- |
| `0.5` | `0x1.0p-1` |
| `1.0` | `0x1.0p0` |
| `2.0` | `0x1.0p1` |
| `3.0` | `0x1.8p1` |
| `Math.nextUp(1.0)` | `0x1.0000000000001p0` |
| `Double.MIN_NORMAL` | `0x1.0p-1022` |
| `Double.MAX_VALUE` | `0x1.fffffffffffffp1023` |

Với `float`:

| Giá trị | `Float.toHexString` |
| --- | --- |
| `1.0f` | `0x1.0p0` |
| `Math.nextUp(1.0f)` | `0x1.000002p0` |
| `Float.MIN_NORMAL` | `0x1.0p-126` |

Đặc biệt, `Double.MAX_VALUE` có phần trị ngay dưới 2 nhân với `2^1023`. Đó là số `double` **hữu hạn lớn nhất**, không phải Infinity; chuỗi hex `0x1.fffffffffffffp1023` giúp nhìn chính xác giới hạn fraction và mũ.

Khi `Math.nextUp(1.0)` thêm bước ULP nhỏ nhất phía trên, bit fraction cuối thay đổi:

```text
1.0                  0x1.0p0
nextUp(1.0)          0x1.0000000000001p0
Math.ulp(1.0)        0x1.0p-52
```

Hex floating-point là công cụ kiểm thử đặc biệt tốt ở các ranh giới **làm tròn**, **số mũ**, và các hàm số có sai số chỉ vài ULP mà cách in decimal mặc định đôi khi khó theo dõi.

## 6. Subnormal: vì sao xuất hiện `0x0....p-1022`?

Các số dương nhỏ nhất của `double` thuộc miền **subnormal**, tức dưới `Double.MIN_NORMAL`. Trong miền này không có bit `1` đầu ẩn của significand normal. Vì thế chuỗi `toHexString` có dạng **`0x0.fractionp-1022`**.

Ví dụ Java 17:

```java
System.out.println(Double.toHexString(Double.MIN_NORMAL));
// 0x1.0p-1022

System.out.println(Double.toHexString(Double.MIN_VALUE));
// 0x0.0000000000001p-1022
```

Ở đây:

- `Double.MIN_NORMAL = 2^-1022`: số dương **normal** nhỏ nhất.
- `Double.MIN_VALUE = 2^-1074`: số `double` **dương nhỏ nhất khác 0**, là subnormal.
- Trong chuỗi `0x0.0000000000001p-1022`, fraction cuối có giá trị `16^-13 = 2^-52`; nhân `2^-1022` cho `2^-1074`.

Với `float`, sự khác biệt tương tự nhưng số mũ và độ rộng khác:

```java
System.out.println(Float.toHexString(Float.MIN_NORMAL));
// 0x1.0p-126

System.out.println(Float.toHexString(Float.MIN_VALUE));
// 0x0.000002p-126
```

`Float.MIN_VALUE = 2^-149` và phần `0x0.000002` tương ứng `2^-23`; nhân thêm `2^-126` ra `2^-149`.

**Đừng nhầm `Double.MIN_VALUE` là số âm nhỏ nhất**. Đây là giá trị dương gần 0 nhất; số hữu hạn âm có độ lớn lớn nhất là `-Double.MAX_VALUE`.

## 7. `+0.0`, `-0.0` và dấu trong chuỗi hex

Java dùng IEEE 754 với **hai mẫu bit zero**:

```java
System.out.println(Double.toHexString(+0.0)); // 0x0.0p0
System.out.println(Double.toHexString(-0.0)); // -0x0.0p0
System.out.println(-0.0 == +0.0);             // true
```

Hai zero so sánh bằng nhau bằng toán tử `==`, nhưng khác **bit dấu**. `toHexString` giữ khác biệt bằng dấu `-` đầu chuỗi.

Điều này quan trọng nếu bạn cần phân biệt kết quả tại các biên hoặc xác minh **round-trip bit-level**. Parse lại `"-0x0.0p0"` bằng `Double.parseDouble` cho mẫu bit negative zero; không nên dựa vào so sánh `==` để kiểm tra hai mẫu zero.

Một cách kiểm tra rõ ràng:

```java
double original = -0.0;
double parsed = Double.parseDouble(Double.toHexString(original));
boolean sameBits = Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(parsed); // true
```

`Math.signum`, phép chia cho zero và các phép toán khác cũng có thể biểu hiện khác nhau với hai dấu zero. Không tự bỏ dấu âm khỏi kết quả hex nếu bạn muốn giữ nguyên ý nghĩa của giá trị dấu phẩy động.

## 8. `NaN` và Infinity không được in như số hex hữu hạn

Hai phương thức `toHexString` trả **tên giá trị đặc biệt** thay vì dựng một số `0x...`:

| Đầu vào | Chuỗi kết quả |
| --- | --- |
| `Double.NaN`, `Float.NaN` | `"NaN"` |
| `Double.POSITIVE_INFINITY`, `Float.POSITIVE_INFINITY` | `"Infinity"` |
| `Double.NEGATIVE_INFINITY`, `Float.NEGATIVE_INFINITY` | `"-Infinity"` |

Ví dụ:

```java
Double.toHexString(Double.NaN);               // "NaN"
Double.toHexString(Double.POSITIVE_INFINITY); // "Infinity"
Double.toHexString(Double.NEGATIVE_INFINITY); // "-Infinity"
```

`NaN` (Not a Number) có thể có **nhiều mẫu bit payload**, nhưng `toHexString` trả một chuỗi chung `"NaN"`. Vì vậy **không thể dùng kết quả `toHexString` để giữ nguyên payload NaN**. Khi cần chính xác từng bit của giá trị `NaN`, phải sử dụng API raw bits phù hợp và một định dạng truyền tải lưu toàn bộ bit.

`Double.parseDouble("NaN")` có thể tạo một mẫu NaN hợp lệ nhưng không biết payload của giá trị ban đầu. Tương tự, `Float.parseFloat("NaN")` không phục hồi payload `float` ban đầu. Phân biệt **round-trip về giá trị đặc biệt** với **round-trip bit-for-bit**.

## 9. Parse ngược: `Double.parseDouble` và `Float.parseFloat`

`Double.parseDouble` và `Float.parseFloat` chấp nhận cả ký pháp số thực thập phân và **hex floating-point**, miễn chuỗi đúng quy tắc parser:

```java
double d = Double.parseDouble("0x1.8p1");  // 3.0
float f = Float.parseFloat("0x1.8p1");    // 3.0f

double x = 0.1;
String hex = Double.toHexString(x);
double restored = Double.parseDouble(hex);
```

Đối với số **hữu hạn**, dạng chuỗi từ `Double.toHexString` chứa đủ thông tin để parse lại thành **cùng mẫu bit `double`** trong cùng quy tắc Java. Tương tự với `Float.toHexString` và `Float.parseFloat` cho `float`.

Chuỗi hex `"0x1.8p1"` khác chuỗi hex nguyên `"1A"`; không truyền nó vào `Integer.parseInt(...,16)` để mong lấy giá trị số thực. Đối với hex floating-point, **`p` và số mũ nhị phân** là thành phần cú pháp chính.

Ví dụ kiểm tra round-trip:

```java
double original = Math.PI;
String valueAsText = Double.toHexString(original);
double reconstructed = Double.parseDouble(valueAsText);

boolean sameRawBits =
        Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(reconstructed);
```

Trong trường hợp `Math.PI` hữu hạn, `sameRawBits` là `true`. Với `NaN`, payload là ngoại lệ cần xử lý riêng; với Infinity, chuỗi vẫn nhận diện đúng vô cực nhưng không chứa bất kỳ fraction số thực nào.

## 10. `toHexString` khác với `toString` và định dạng thập phân

| Cách hiển thị | Ví dụ với `double 0.1` | Mục đích |
| --- | --- | --- |
| `Double.toString(x)` | `0.1` | Biểu diễn thập phân ngắn, dễ đọc, hỗ trợ round-trip theo quy tắc Java |
| `Double.toHexString(x)` | `0x1.999999999999ap-4` | Lộ rõ giá trị nhị phân được lưu dưới dạng significand hex và mũ 2 |
| `String.format("%.2f", x)` | `0.10` | Trình bày số thập phân theo precision/locale, có thể làm tròn chuỗi đầu ra |
| `Double.doubleToRawLongBits(x)` | `long` 64 bit | Lấy mẫu bit dấu, exponent, fraction; không phải định dạng số thực text |

Đây là những nhiệm vụ khác nhau. `Double.toString(0.1)` in `0.1` vì đó là biểu diễn thập phân ngắn phù hợp cho giá trị `double`, **không chứng minh giá trị đã lưu bằng đúng phân số thập phân 1/10**.

Nếu mục tiêu chỉ là báo cáo giá/đơn vị cho người đọc, chuỗi hex có thể khó hiểu và không phù hợp. Nếu mục tiêu là **kiểm tra sai số số học, hiệu ứng làm tròn, khoảng cách ULP, normal/subnormal** thì chuỗi hex giúp tránh mơ hồ về phần trị nhị phân.

`String.format("%a", x)` cũng là một cách trình bày hex floating-point trong hệ thống formatter của Java, nhưng khác về API, cấu hình locale và precision. Khi cần một cách in ngắn gọn, nhất quán, không phụ thuộc vào format string, `Double.toHexString`/`Float.toHexString` là lựa chọn trực tiếp.

## 11. Phân biệt `Double.toHexString` và raw IEEE 754 bits

Đây là **hai cách biểu diễn khác nhau** cho cùng giá trị `1.0`:

```java
System.out.println(Double.toHexString(1.0));
// 0x1.0p0

System.out.println(Long.toHexString(Double.doubleToRawLongBits(1.0)));
// 3ff0000000000000
```

Chuỗi đầu là **giá trị toán học biểu diễn bằng phần trị hex nhân lũy thừa 2**. Chuỗi sau là **64 bit dữ liệu IEEE 754 dưới dạng một số nguyên `long` biểu diễn hex**, gồm cả bit dấu, exponent đã bias và fraction trong các vị trí bit cố định.

Tương tự với `float`:

```java
System.out.println(Float.toHexString(1.0f));
// 0x1.0p0

System.out.println(Integer.toHexString(Float.floatToRawIntBits(1.0f)));
// 3f800000
```

Một số người mới học thấy `toHexString` rồi tưởng nó in raw bit pattern. Dấu hiệu nhận biết:

- **Dạng giá trị dấu phẩy động:** thường `0x1.xxxxxpE`, `0x0.xxxpE`, `-0x0.0p0`, `NaN` hoặc `Infinity`.
- **Dạng raw bit pattern:** dùng `Long.toHexString`/`Integer.toHexString` trên giá trị trả về của `doubleToRawLongBits`/`floatToRawIntBits`, là chuỗi hex **không có `p`**.

`Double.doubleToLongBits` (không có `Raw`) **chuẩn hóa NaN** thành mẫu canonical; nếu bài toán cần quan sát payload, dùng `Double.doubleToRawLongBits`. Tương tự với `Float.floatToIntBits` so với `Float.floatToRawIntBits`.

Và không được nhầm **raw bits** với **thứ tự byte (endianness)** trên mạng hoặc trong tệp. Muốn serialization byte-for-byte, bạn còn phải chọn byte order và bố cục trường dữ liệu; chỉ tạo chuỗi `0x1.0p0` không quyết định bộ bốn/tám byte được truyền ra ngoài.

## 12. Ví dụ Java 17+ độc lập và stdout đã kiểm chứng

Lưu thành tệp **`FloatingHexDemo.java`**:

```java
public class FloatingHexDemo {
    private static void showDouble(String name, double x) {
        System.out.println(name + "=" + Double.toHexString(x));
    }

    private static void showFloat(String name, float x) {
        System.out.println(name + "=" + Float.toHexString(x));
    }

    public static void main(String[] args) {
        showDouble("dZero", 0.0);
        showDouble("dNegativeZero", -0.0);
        showDouble("dOne", 1.0);
        showDouble("dHalf", 0.5);
        showDouble("dThree", 3.0);
        showDouble("dPointOne", 0.1);
        showDouble("dMinNormal", Double.MIN_NORMAL);
        showDouble("dMinSubnormal", Double.MIN_VALUE);
        showDouble("dMaxFinite", Double.MAX_VALUE);
        showDouble("dNextUpOne", Math.nextUp(1.0));
        showDouble("dPositiveInfinity", Double.POSITIVE_INFINITY);
        showDouble("dNegativeInfinity", Double.NEGATIVE_INFINITY);
        showDouble("dNaN", Double.NaN);

        showFloat("fOne", 1.0f);
        showFloat("fPointOne", 0.1f);
        showFloat("fMinNormal", Float.MIN_NORMAL);
        showFloat("fMinSubnormal", Float.MIN_VALUE);
        showFloat("fNextUpOne", Math.nextUp(1.0f));
        showFloat("fNegativeZero", -0.0f);

        System.out.println("parseHexDouble="
                + Double.parseDouble("0x1.8p1"));
        System.out.println("parseHexFloat="
                + Float.parseFloat("0x1.8p1"));
        System.out.println("negativeZeroEqualsPositiveZero="
                + (-0.0 == 0.0));
        System.out.println("negativeZeroRoundTripBits="
                + (Double.doubleToRawLongBits(-0.0)
                == Double.doubleToRawLongBits(
                        Double.parseDouble(Double.toHexString(-0.0)))));

        String textDouble = Double.toHexString(Math.PI);
        double parsedDouble = Double.parseDouble(textDouble);
        System.out.println("doubleRoundTripBits="
                + (Double.doubleToRawLongBits(Math.PI)
                == Double.doubleToRawLongBits(parsedDouble)));

        String textFloat = Float.toHexString(0.1f);
        float parsedFloat = Float.parseFloat(textFloat);
        System.out.println("floatRoundTripBits="
                + (Float.floatToRawIntBits(0.1f)
                == Float.floatToRawIntBits(parsedFloat)));

        System.out.println("floatOneRawBits="
                + Integer.toHexString(Float.floatToRawIntBits(1.0f)));
        System.out.println("doubleOneRawBits="
                + Long.toHexString(Double.doubleToRawLongBits(1.0)));

        double nanPayload = Double.longBitsToDouble(0x7ff8000000000001L);
        String nanText = Double.toHexString(nanPayload);
        System.out.println("nanText=" + nanText);
        System.out.println("nanPayloadLost="
                + (Double.doubleToRawLongBits(nanPayload)
                != Double.doubleToRawLongBits(Double.parseDouble(nanText))));
    }
}
```

Biên dịch/chạy tại thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 FloatingHexDemo.java
java FloatingHexDemo
```

Stdout chính xác:

```text
dZero=0x0.0p0
dNegativeZero=-0x0.0p0
dOne=0x1.0p0
dHalf=0x1.0p-1
dThree=0x1.8p1
dPointOne=0x1.999999999999ap-4
dMinNormal=0x1.0p-1022
dMinSubnormal=0x0.0000000000001p-1022
dMaxFinite=0x1.fffffffffffffp1023
dNextUpOne=0x1.0000000000001p0
dPositiveInfinity=Infinity
dNegativeInfinity=-Infinity
dNaN=NaN
fOne=0x1.0p0
fPointOne=0x1.99999ap-4
fMinNormal=0x1.0p-126
fMinSubnormal=0x0.000002p-126
fNextUpOne=0x1.000002p0
fNegativeZero=-0x0.0p0
parseHexDouble=3.0
parseHexFloat=3.0
negativeZeroEqualsPositiveZero=true
negativeZeroRoundTripBits=true
doubleRoundTripBits=true
floatRoundTripBits=true
floatOneRawBits=3f800000
doubleOneRawBits=3ff0000000000000
nanText=NaN
nanPayloadLost=true
```

Phân tích kết quả:

1. **Nhóm `dZero` đến `dThree`:** minh họa dấu, phần trị hex và số mũ nhị phân; số 3 được biểu diễn `0x1.8p1`.
2. **`dPointOne` và `fPointOne`:** cùng ý tưởng `0.1` nhưng hai kiểu lưu các bit fraction khác nhau; `float` ít chính xác hơn `double`.
3. **`dMinNormal`, `dMinSubnormal`, `fMinNormal`, `fMinSubnormal`:** ranh giới normal/subnormal và dạng `0x0....pE`.
4. **`dNextUpOne`, `fNextUpOne`:** quan sát một bước lưới floating-point của mỗi kiểu.
5. **`dPositiveInfinity`, `dNegativeInfinity`, `dNaN`:** các trường hợp đặc biệt không xuất dạng hex significand.
6. **`parseHexDouble`, `parseHexFloat`:** `parseDouble` và `parseFloat` nhận chuỗi có ký hiệu `p` và trả giá trị 3.
7. **`negativeZeroRoundTripBits`, `doubleRoundTripBits`, `floatRoundTripBits`:** xác minh parse ngược giữ mẫu bit của các giá trị hữu hạn được thử, gồm dấu âm của zero.
8. **`floatOneRawBits`, `doubleOneRawBits`:** minh họa raw IEEE bits **khác** `toHexString`.
9. **`nanPayloadLost=true`:** chuỗi `"NaN"` không mã hóa payload của mẫu NaN được tạo ra từ raw bits.

Chương trình dùng hàm `showDouble`/`showFloat` để tránh lặp lời gọi `println`. Chỉ có một `public class FloatingHexDemo`, tên trùng file, không cần thư viện ngoài Java 17.

## 13. Ứng dụng khi debug ULP, số kề và lỗi làm tròn

Giả sử một thuật toán dự kiến cho kết quả `1.0`, nhưng thực tế trả giá trị `double` ngay kế trên:

```java
double exact = 1.0;
double actual = Math.nextUp(exact);

System.out.println(Double.toHexString(exact));  // 0x1.0p0
System.out.println(Double.toHexString(actual)); // 0x1.0000000000001p0
System.out.println(Double.toHexString(Math.ulp(exact))); // 0x1.0p-52
```

Chỉ một chữ số phần trị hex cuối được thay đổi. Điều đó cho phép nhận diện cụ thể một bước gần `1.0`, thay vì ghi chung “sai số nhỏ”. Nhưng cần cẩn thận: tại **ranh giới lũy thừa 2**, khoảng cách phía trên và phía dưới có thể khác nhau. `Math.ulp(1.0)` bằng `2^-52`, trong khi `1.0-Math.nextDown(1.0)` bằng `2^-53`. Đừng coi mọi số `double` ở gần nhau là nằm trên lưới có bước cố định toàn cục.

Khi so sánh output của hai thuật toán, `toHexString` giúp thấy sự khác biệt **mẫu phần trị được biểu diễn**. Dù vậy, **khác vài chữ số hex không tự xác định thuật toán nào đúng hơn**: cần một đáp án tham chiếu, thang sai số (tuyệt đối/tương đối/ULP) và điều kiện bài toán.

Trong kiểm thử biên, có thể lưu cả output decimal lẫn hex để vừa dễ đọc vừa dễ phân tích:

```java
double result = Math.nextUp(1.0);
System.out.println("decimal=" + result);
System.out.println("hex=" + Double.toHexString(result));
```

## 14. Ứng dụng khi trao đổi dữ liệu

Nếu API trao đổi **chuỗi văn bản** được quy định rõ là cú pháp Java hex floating-point, có thể dùng:

```java
String payload = Double.toHexString(0.1);
double received = Double.parseDouble(payload);
```

Đối với **giá trị hữu hạn**, phép parse lại có thể giữ chính xác mẫu bit `double` của giá trị ban đầu. Hãy ghi rõ trong tài liệu API rằng đây là **chuỗi số thực hex với `p`**, không phải unsigned integer hex hoặc dữ liệu 8 byte nhị phân.

Tuy nhiên, cần cân nhắc:

- **Ngôn ngữ/bên nhận:** nhiều ngôn ngữ hỗ trợ dạng hex floating-point tương đương, nhưng không phải mọi thư viện JSON, CSV hoặc parser số đều chấp nhận `0x1.8p1`.
- **Các giá trị đặc biệt:** `NaN`, `Infinity`, `-Infinity` cần quy ước riêng, nhất là trong chuẩn trao đổi JSON vốn không coi chúng là number hợp lệ.
- **Giá trị NaN với payload:** không round-trip bit-exact qua `"NaN"`.
- **Tính chuẩn hóa đầu vào:** parser có thể chấp nhận những chuỗi tương đương; nếu cần canonical representation để băm/ký dữ liệu, hãy định nghĩa rõ format và kiểm tra chuỗi canonical chứ không chỉ parse thành công.
- **An toàn:** kiểm tra giới hạn độ dài, kiểu hợp lệ và miền nghiệp vụ trước khi tin input. Parser Java báo `NumberFormatException` đối với chuỗi sai cú pháp nhưng không biết giới hạn logic ứng dụng.

Nếu hợp đồng yêu cầu gửi **đúng 32/64 bit raw** của một giá trị IEEE 754, hãy dùng `floatToRawIntBits`/`doubleToRawLongBits`, định nghĩa rõ byte order, rồi mã hóa thành byte hoặc hex bit pattern 8/16 chữ số. Đó là **một định dạng khác** với `toHexString`.

## 15. Lỗi phổ biến và cách khắc phục

| Nhầm lẫn | Thực tế | Cách làm đúng |
| --- | --- | --- |
| `Double.toHexString(3.0)` trả `"3"` hoặc `"0x3"` | Trả `"0x1.8p1"` | Nhớ phần trị hex và mũ cơ số 2 |
| Ký tự `p` là lũy thừa 10 | `pE` nghĩa nhân `2^E` | Diễn giải theo cơ số 2 |
| `Float.toHexString` có độ chính xác như `Double.toHexString` | Float có 24 bit significand, double có 53 | Giữ đúng kiểu cần kiểm tra |
| Hàm xuất ra raw IEEE bit pattern | Hàm biểu diễn **giá trị số thực**, không phải bit fields | Dùng `floatToRawIntBits`/`doubleToRawLongBits` |
| `Double.MIN_VALUE` là số âm nhỏ nhất | Đây là positive subnormal nhỏ nhất | Phân biệt `MIN_NORMAL`, `MIN_VALUE`, `MAX_VALUE` |
| Mọi giá trị có dạng `0x1.xxxpE` | Subnormal có dạng `0x0.xxxpE` | Kiểm tra ranh giới subnormal |
| `-0.0` và `+0.0` phải có cùng chuỗi | `toHexString` giữ dấu `-0.0` | Test cả hai mẫu zero |
| `NaN` trong hex chứa toàn bộ payload | Chuỗi trả `"NaN"` chung | Dùng raw bits nếu cần bit-exact |
| `Integer.parseInt("0x1.8p1",16)` đọc được float hex | Không phải cú pháp số nguyên | Dùng `Double.parseDouble`/`Float.parseFloat` |
| `0.1` in dưới dạng decimal thì lưu chính xác 1/10 | `double` làm tròn nhị phân | Dùng hex output để quan sát, hoặc `BigDecimal` cho decimal exact |
| Hex floating-point tự nói lên endian trong bộ nhớ | Endian áp dụng cho thứ tự byte của serialization | Định nghĩa byte order riêng |
| Thấy hai chuỗi hex khác thì biết ngay sai số thuật toán | Hex chỉ cho thấy khác biệt biểu diễn | So với đáp án tham chiếu và ngưỡng lỗi |

## 16. Câu hỏi tự kiểm tra

1. **`Double.toHexString(3.0)` trả gì?** `"0x1.8p1"` vì `(1+8/16)×2=3`.
2. **`0x1.0p-1` bằng mấy?** `0.5`.
3. **Số mũ `p5` nghĩa nhân với `2^5` hay `16^5`?** Nhân `2^5`.
4. **Vì sao `Double.toHexString(0.1)` nhiều chữ số hex còn `Double.toString(0.1)` chỉ in `0.1`?** Chuỗi hex thể hiện chính xác significand/mũ nhị phân được lưu; chuỗi decimal ngắn tối ưu cách hiển thị, không ngụ ý lưu chính xác 1/10.
5. **`Double.MIN_VALUE` xuất thành dạng normal `0x1...pE` không?** Không: `0x0.0000000000001p-1022`, vì đó là subnormal dương nhỏ nhất.
6. **`Float.MIN_VALUE` xuất gì?** `0x0.000002p-126`.
7. **`Double.toHexString(-0.0)` khác `Double.toHexString(+0.0)` ở đâu?** Dấu âm, `-0x0.0p0` so với `0x0.0p0`.
8. **`Double.toHexString(Double.NaN)` có lưu được payload NaN không?** Không, chỉ `"NaN"`; phải dùng raw bits nếu cần payload.
9. **Parse ngược `0x1.8p1` dùng gì?** `Double.parseDouble("0x1.8p1")` hoặc `Float.parseFloat(...)`, không phải `Integer.parseInt`.
10. **Muốn in cả 64 bit của `double 1.0` phải gọi API nào?** `Long.toHexString(Double.doubleToRawLongBits(1.0))`; kết quả là `"3ff0000000000000"`, không phải `"0x1.0p0"`.
11. **Tại `1.0`, `Math.nextUp(1.0)` xuất chuỗi gì?** `0x1.0000000000001p0`: một bước biểu diễn phía trên.
12. **Dùng `toHexString` để gửi binary wire format có đủ không?** Không. Đây là chuỗi văn bản; wire format nhị phân phải định nghĩa byte order, độ rộng và cách xử lý giá trị đặc biệt riêng.

**Ghi nhớ:** `Double.toHexString` và `Float.toHexString` biểu diễn **giá trị dấu phẩy động nhị phân** dưới dạng `0xH.FpE`, trong đó **fraction viết bằng hex, số mũ là lũy thừa của 2**. Dạng này đặc biệt hữu ích để debug precision, ULP, normal/subnormal và signed zero. Muốn parse ngược thì dùng `Double.parseDouble`/`Float.parseFloat`; muốn giữ đúng raw IEEE bit pattern hoặc payload NaN thì dùng các API **RawBits**, không nhầm chúng với `toHexString`.
