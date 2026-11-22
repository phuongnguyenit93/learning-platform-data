# Float.parseFloat, Double.parseDouble và valueOf trong Java

## 1. Mục tiêu: cùng chuỗi số thực, khác kiểu trả về

Trong Java, một chuỗi như `"3.5"` có thể được phân tích thành giá trị số thực primitive hoặc thành đối tượng wrapper:

```java
float f = Float.parseFloat("3.5");
Float boxedF = Float.valueOf("3.5");

double d = Double.parseDouble("3.5");
Double boxedD = Double.valueOf("3.5");
```

Cả bốn biến cùng thể hiện giá trị toán học 3,5 ở ví dụ trên, nhưng **kiểu dữ liệu và cách làm việc với chúng khác nhau**:

| Phương thức | Kiểu đầu vào | Kiểu trả về | Vai trò |
| --- | --- | --- | --- |
| `Float.parseFloat(String)` | `String` | primitive `float` | Phân tích về binary32 |
| `Float.valueOf(String)` | `String` | wrapper `Float` | Phân tích và trả đối tượng chứa binary32 |
| `Double.parseDouble(String)` | `String` | primitive `double` | Phân tích về binary64 |
| `Double.valueOf(String)` | `String` | wrapper `Double` | Phân tích và trả đối tượng chứa binary64 |

Bài này thuộc **Java Core — Numbers / Phân tích số thực**. Sau khi hoàn thành, bạn cần:

1. Đọc đúng chữ ký và chọn `parseFloat`/`parseDouble` khi cần primitive, `valueOf(String)` khi cần wrapper.
2. Hiểu **precision 32 bit so với 64 bit**: thay `Float` bằng `Double` không chỉ đổi lớp object mà còn đổi độ chính xác và miền giá trị.
3. Nhận diện parser có ngữ pháp số riêng, lỗi cú pháp và giá trị đặc biệt cần xác thực tách biệt.
4. Đọc được hiệu ứng boxing/unboxing, overload, wrapper equality, signed zero và NaN.
5. Tự chạy và giải thích ví dụ Java 17+ về kiểu trả về, precision và so sánh.

**Nguyên tắc chính:** `parseFloat` khác `Float.valueOf(String)` ở **kiểu trả về**; `parseDouble` khác `Double.valueOf(String)` tương tự. Nhưng `Float` và `Double` lại **khác nhau về định dạng số nhị phân và độ chính xác**. Không được gộp hai loại khác biệt này thành một.

## 2. Parse trả primitive, valueOf(String) trả wrapper

Hai cặp phương thức có chữ ký chuẩn:

```text
public static float  Float.parseFloat(String s)
public static Float  Float.valueOf(String s)
public static double Double.parseDouble(String s)
public static Double Double.valueOf(String s)
```

Các dòng trên là **cách ghi chữ ký để minh họa**, không phải mã Java dùng để khai báo lớp mới.

### 2.1. Cùng cách đọc chuỗi, khác kiểu đích

`Float.valueOf(s)` phân tích chuỗi theo cùng ngữ nghĩa như `Float.parseFloat(s)` và trả một `Float` chứa giá trị `float` thu được. `Double.valueOf(s)` tương tự với `Double.parseDouble(s)` và wrapper `Double`.

```java
float raw = Float.parseFloat("2.75");
Float object = Float.valueOf("2.75");

System.out.println(raw);       // 2.75
System.out.println(object);    // 2.75
```

Stdout giống nhau vì `println` hỗ trợ cả primitive và object. **Không được suy từ dòng in** rằng hai biểu thức có cùng kiểu compile-time.

### 2.2. Khác biệt kiểu ảnh hưởng tính toán hay API object

Primitive `float`/`double` phù hợp với toán học và các API nhận primitive. Wrapper `Float`/`Double` là đối tượng immutable, có thể:

- Được lưu trong `List<Float>` hoặc `Map<String,Double>`.
- Có thể nằm trong biến tham chiếu nhận `null` để biểu diễn trạng thái thiếu dữ liệu, nếu thiết kế cho phép.
- Cung cấp các phương thức instance như `equals`, `compareTo` và `hashCode`.
- Được dùng với generics vốn **không nhận primitive** làm type argument.

Điều này không có nghĩa mọi lời gọi `valueOf` đều buộc JVM tạo đối tượng mới. Wrapper có thể được tái sử dụng tùy chính sách implementation/API. **Không dựa vào tham chiếu `==` để kiểm tra cùng giá trị số** giữa hai đối tượng wrapper.

## 3. Boxing và unboxing làm hai cách viết trông giống nhau

Java có autoboxing/unboxing:

```java
float a = Float.parseFloat("1.25");    // float -> float
Float b = Float.valueOf("1.25");      // Float -> Float

Float c = Float.parseFloat("1.25");   // boxing float -> Float
float d = Float.valueOf("1.25");      // unboxing Float -> float

double e = Double.parseDouble("1.25"); // double -> double
Double f = Double.valueOf("1.25");     // Double -> Double

Double g = Double.parseDouble("1.25");// boxing double -> Double
double h = Double.valueOf("1.25");    // unboxing Double -> double
```

Cả tám phép gán đều hợp lệ. **Kiểu trả về gốc của phương thức không đổi** khi biến bên trái có kiểu khác: compiler chỉ áp dụng conversion được phép trong ngữ cảnh gán.

| Biểu thức nguồn | Biến đích | Bước bổ sung |
| --- | --- | --- |
| `Float.parseFloat(s)` | `float` | Không |
| `Float.parseFloat(s)` | `Float` | Boxing |
| `Float.valueOf(s)` | `Float` | Không |
| `Float.valueOf(s)` | `float` | Unboxing |
| `Double.parseDouble(s)` | `double` | Không |
| `Double.parseDouble(s)` | `Double` | Boxing |
| `Double.valueOf(s)` | `Double` | Không |
| `Double.valueOf(s)` | `double` | Unboxing |

**Lưu ý:** nếu một biến wrapper được gán `null` bởi nguồn khác, unboxing có thể ném `NullPointerException`:

```java
Double missing = null;
// double result = missing; // runtime NullPointerException
```

Nhưng `Double.valueOf("1.25")` với chuỗi hợp lệ không trả `null`: nó trả một đối tượng `Double`.

## 4. Sự khác nhau giữa float và double không phải chỉ là wrapper

`float` và `double` đều là primitive floating-point theo binary IEEE 754, nhưng có độ rộng và độ chính xác khác nhau.

| Thuộc tính | `float` | `double` |
| --- | --- | --- |
| Khuôn dạng | binary32 | binary64 |
| Độ dài | 32 bit | 64 bit |
| Significand precision | 24 bit | 53 bit |
| Khoảng chữ số thập phân có nghĩa hữu dụng gần đúng | 6–9 | 15–17 |
| Hằng số dương hữu hạn lớn nhất | `Float.MAX_VALUE` | `Double.MAX_VALUE` |
| Số dương khác 0 nhỏ nhất (subnormal) | `Float.MIN_VALUE` | `Double.MIN_VALUE` |
| Hàm phân tích | `Float.parseFloat(s)` | `Double.parseDouble(s)` |

Các số thập phân như `0.1` hầu hết không thể lưu đúng tuyệt đối trong biểu diễn nhị phân hữu hạn. `Float.parseFloat("0.1")` được làm tròn trực tiếp sang `float`; `Double.parseDouble("0.1")` được làm tròn sang `double`. Từ đó, **hai giá trị có thể khác nhau khi cùng được đưa về kiểu `double` để so sánh**.

### 4.1. Ví dụ độ chính xác

```java
float f = Float.parseFloat("0.1");
double d = Double.parseDouble("0.1");

System.out.println(f);           // 0.1
System.out.println(d);           // 0.1
System.out.println((double) f);  // 0.10000000149011612
System.out.println(f == d);      // false
```

Dòng in `0.1` cho `float` là dạng chuỗi thập phân ngắn tái tạo được giá trị khi parse lại; nó **không có nghĩa** `float` lưu đúng 1/10. Mở rộng `float` thành `double` ở dòng thứ ba cho thấy giá trị binary32 sau khi làm tròn.

Đặc biệt:

- `Float.parseFloat("0.1") == 0.1f` là true: cả hai có `float` và cùng giá trị binary32.
- `Float.parseFloat("0.1") == 0.1` là false: bên phải là `double`, còn `float` bên trái được widening nhưng không lấy lại bit chính xác đã mất.
- Khi cần biểu diễn thập phân chính xác theo nghiệp vụ, nên cân nhắc `BigDecimal` tạo trực tiếp từ **chuỗi gốc**, không cố nâng `float` thành `double` để “chữa” sai số.

### 4.2. Không parse về double rồi cast về float một cách máy móc

`(float) Double.parseDouble(s)` có thể trông giống `Float.parseFloat(s)`, nhưng Java/JDK cung cấp parser `float` riêng để làm tròn giá trị decimal theo quy tắc của **binary32**. Việc làm tròn trước sang binary64 rồi thu hẹp sang binary32 có thể tạo **double-rounding** tại các trường hợp ranh giới tinh vi.

Nếu yêu cầu là giá trị `float` được đọc từ chuỗi, **ưu tiên `Float.parseFloat(s)`**; không cần đi vòng qua `Double.parseDouble`. Nếu yêu cầu thực sự là `double`, dùng `Double.parseDouble` và giữ kiểu phù hợp trong các bước tính toán.

## 5. Parse thành công và validation là hai tầng riêng

`Double.parseDouble`/`Float.parseFloat` hỗ trợ số decimal (`"1.25"`, `"1e3"`), hexadecimal floating-point (`"0x1.8p1"`), suffix f/d và các token `NaN`, `Infinity`. Hậu tố không thay đổi kiểu trả về do API quy định. Chuỗi không đúng ngữ pháp như `"1_000.0"`, `"1,5"` và `"0x1.8"` gây `NumberFormatException`; đầu vào null gây `NullPointerException`.

Chuỗi hợp lệ nhưng quá lớn hoặc quá nhỏ có thể được làm tròn thành vô cực hoặc zero; `isFinite` loại NaN và Infinity nhưng không chứng minh không mất precision. Cú pháp chi tiết, số đặc biệt, rounding, locale, decimal exactness và validation miền được giải thích chuyên sâu ở những bài riêng của chương. Khi dùng `parseFloat` hay `parseDouble`, luôn lựa chọn kiểu đích trước và kiểm tra miền dữ liệu của kết quả.

## 6. Chương trình chạy được A: kiểu trả về và overload

Lưu thành **`FloatingParseTypes.java`**:

```java
public class FloatingParseTypes {
    static String describe(float x) {
        return "float " + x;
    }

    static String describe(Float x) {
        return "Float " + x;
    }

    static String describe(double x) {
        return "double " + x;
    }

    static String describe(Double x) {
        return "Double " + x;
    }

    public static void main(String[] args) {
        float primitiveFloat = Float.parseFloat("3.5");
        Float boxedFloat = Float.valueOf("3.5");
        double primitiveDouble = Double.parseDouble("3.5");
        Double boxedDouble = Double.valueOf("3.5");

        System.out.println(describe(primitiveFloat));
        System.out.println(describe(boxedFloat));
        System.out.println(describe(primitiveDouble));
        System.out.println(describe(boxedDouble));

        System.out.println(boxedFloat.getClass().getSimpleName());
        System.out.println(boxedDouble.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 FloatingParseTypes.java
java FloatingParseTypes
```

**Stdout:**

```text
float 3.5
Float 3.5
double 3.5
Double 3.5
Float
Double
```

Bốn lời gọi `describe` chọn overload dựa trên **kiểu biểu thức** ở chỗ gọi, không dựa trên việc `"3.5"` trông như số thực thập phân. Đây là cách chứng minh thực tế sự khác nhau về kiểu trả về khi `println` mặc định lại in cùng dạng.

## 7. Wrapper equality, identity, NaN và signed zero

`Float.valueOf(String)`/`Double.valueOf(String)` trả đối tượng wrapper nên có hai kiểu so sánh dễ bị lẫn.

### 7.1. Hai wrapper: `equals` thay vì `==`

```java
Float a = Float.valueOf("1.5");
Float b = Float.valueOf("1.5");

System.out.println(a.equals(b)); // true
```

`a.equals(b)` dùng quy tắc equality của `Float`. `a == b` giữa hai reference `Float` xét **object identity**, có thể phụ thuộc caching; không nên dùng để hỏi hai số có cùng giá trị.

Nếu một bên là primitive `float`, phép `==` có thể unbox wrapper và so primitive:

```java
float raw = Float.parseFloat("1.5");
Float boxed = Float.valueOf("1.5");
System.out.println(raw == boxed); // true
```

Đừng suy mọi `==` viết với wrapper đều là phép so cùng kiểu giá trị; phải xem compile-time types của **cả hai** toán hạng.

### 7.2. `Float` khác `Double` theo `equals`

```java
System.out.println(Float.valueOf("1.5")
        .equals(Double.valueOf("1.5"))); // false
```

Hai wrapper khác class, nên `Float.equals` không coi `Double` tương đương, ngay cả khi cùng lượng toán học đúng 1.5. Nếu một API trộn `Number` hoặc nhiều wrapper, phải có chính sách dữ liệu rõ ràng.

### 7.3. NaN và signed zero

```java
System.out.println(Double.parseDouble("NaN")
        == Double.parseDouble("NaN")); // false

System.out.println(Double.valueOf("NaN")
        .equals(Double.valueOf("NaN"))); // true

System.out.println(Double.parseDouble("-0.0")
        == Double.parseDouble("0.0")); // true

System.out.println(Double.valueOf("-0.0")
        .equals(Double.valueOf("0.0"))); // false
```

Quy tắc này đến từ **primitive equality** và **wrapper equality**, không phải vì chuỗi `"NaN"` hay `"-0.0"` được parse “khác tiêu chuẩn” bởi `valueOf`.

`Double.compare(-0.0,+0.0)` cũng phân biệt hai zero và đặt zero âm trước zero dương. Với `Double.NaN`, `Double.compare` có thứ tự riêng phù hợp cho wrapper ordering. Khi dùng `HashSet<Double>` hoặc `TreeSet<Double>`, cần hiểu các quy tắc này thay vì tùy tiện thêm epsilon vào `equals` hoặc comparator.

## 8. valueOf có những overload nào?

Tên `valueOf` ở các wrapper xuất hiện với nhiều kiểu tham số, không phải overload nào cũng parse chuỗi:

```java
Float a = Float.valueOf(2.5f);    // valueOf(float), không parse String
Float b = Float.valueOf("2.5");   // valueOf(String), parse chuỗi

Double c = Double.valueOf(2.5);   // valueOf(double), không parse String
Double d = Double.valueOf("2.5"); // valueOf(String), parse chuỗi
```

**Quan trọng:** `Float.valueOf(2.5f)` đã nhận giá trị binary32 có sẵn; `Float.valueOf("2.5")` mới bắt đầu từ ký tự chuỗi. `Double.valueOf(2.5)` nhận một `double` có sẵn.

Nếu nguồn đầu vào là một `float` rồi chuyển sang `Double`:

```java
float f = Float.parseFloat("0.1");
Double wrappedWidened = Double.valueOf((double) f);
```

`wrappedWidened` chứa chính giá trị `float` đã được làm tròn trước rồi widening, **không phải** giá trị binary64 có được từ `Double.valueOf("0.1")`. Chuyển wrapper không thể làm mất những bước làm tròn đã xảy ra biến mất.

## 9. Bài tập củng cố kiểu trả về

1. So sánh kiểu compile-time của `Float.parseFloat("1.5")` và `Float.valueOf("1.5")`; khi đưa vào overload `describe(float)` và `describe(Float)`, lời gọi nào được chọn?
2. Giải thích vì sao `Float f = Float.parseFloat("2.5")` hợp lệ dù `parseFloat` trả primitive.
3. Dự đoán `Float.valueOf("1.5").equals(Double.valueOf("1.5"))` và lý giải hợp đồng wrapper.
4. Nêu lý do `Float.parseFloat("0.1") == Double.parseDouble("0.1")` là false nhưng `Float.parseFloat("0.1") == 0.1f` là true.
5. Chọn parser và kiểu dữ liệu phù hợp cho một bộ đo nhận `double` và một `List<Float>`. Điều kiện nào cần được kiểm tra sau khi parse?

**Đối chiếu:** `parseFloat` trả primitive, `valueOf(String)` trả wrapper; boxing/unboxing không đổi chữ ký. Wrapper khác lớp không `equals` dù cùng lượng toán học, còn giá trị binary32 không bằng binary64 khi decimal 0.1 được làm tròn khác nhau. Chọn API theo kiểu đích, đồng thời xác thực tính hữu hạn/miền theo hợp đồng.

**Tài liệu:** [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html), [JLS boxing/unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).
