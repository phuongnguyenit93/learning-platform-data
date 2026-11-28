# Bật preview và cân nhắc độ ổn định trước khi đưa cú pháp vào mã dùng chung



## 1. Kết luận trước khi thử nghiệm

**Primitive Types in Patterns, instanceof, and switch** là tính năng preview của Java 25 theo **JEP 507 — Third Preview**. Tính năng này mở rộng pattern matching để dùng kiểu nguyên thủy trong các ngữ cảnh pattern, cho phép `instanceof` kiểm tra chuyển đổi giữa các kiểu nguyên thủy và mở rộng `switch` sang mọi kiểu nguyên thủy.

Trạng thái hiện nay đã thay đổi so với thời điểm Java 25 phát hành:

- JDK 23: JEP 455, preview lần đầu.
- JDK 24: JEP 488, preview lần thứ hai.
- JDK 25: JEP 507, preview lần thứ ba.
- JDK 26: JEP 530, preview lần thứ tư; điều chỉnh khái niệm chuyển đổi chính xác vô điều kiện và quy tắc dominance của `switch`.
- JDK 27: JEP 532, preview lần thứ năm.
- Ngày 11/11/2026, nhóm ngôn ngữ Java thông báo **ngừng phát triển tính năng này**. Bản JEP dự kiến cho preview lần thứ sáu bị rút; tính năng sẽ bị loại khỏi JDK 28 và không thể bật lại bằng `--enable-preview`.

Vì vậy, bài học này dùng Java 25 để hiểu cú pháp, quy tắc chuyển đổi và cách đánh giá preview. Bạn có thể thử trong một project nghiên cứu được pin vào JDK 25, hoặc đọc mã hiện có cần duy trì trên đúng runtime đó. **Không nên đưa tính năng này vào thư viện, API hoặc mã dùng chung mới**, bởi nó không trở thành tính năng ngôn ngữ ổn định và sẽ không còn trong JDK 28.

Thông báo rút tính năng cũng nêu lý do thiết kế: Project Valhalla đang nghiên cứu mô hình số mới, bao gồm khả năng có kiểu số do người dùng định nghĩa. Việc chốt quy tắc chuyển đổi số chính xác hiện tại có thể quá sớm khi mô hình số đó còn tiếp tục phát triển.



## 2. Tính năng này giải quyết vấn đề gì?

Trong Java truyền thống, pattern matching chủ yếu làm việc với reference types. Nếu cần kiểm tra một giá trị nguyên thủy có thể chuyển đổi chính xác sang kiểu nhỏ hơn, lập trình viên thường phải tự viết điều kiện biên và ép kiểu.

Ví dụ, muốn chuyển `int` sang `byte` an toàn, mã thông thường phải kiểm tra giới hạn:

```java
static Byte toByteIfInRange(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        return null;
    }
    return (byte) value;
}
```

Primitive type patterns cho phép biểu diễn phép kiểm tra và lấy giá trị sau chuyển đổi trong cùng một pattern:

```java
static String classify(int value) {
    if (value instanceof byte small) {
        return "Giá trị biểu diễn được bằng byte: " + small;
    }
    return "Giá trị nằm ngoài miền byte: " + value;
}
```

Với giá trị `10`, pattern `byte small` khớp. Với `1000`, pattern không khớp vì chuyển đổi sang `byte` sẽ làm mất thông tin.

Điểm quan trọng là pattern không chỉ hỏi “có thể ép kiểu hay không”. Nó kiểm tra liệu chuyển đổi có **chính xác đối với giá trị đang xét** hay không. Điều này giúp tránh trường hợp ép kiểu số làm thay đổi dấu, độ lớn, phạm vi hoặc độ chính xác.



## 3. Phạm vi cú pháp được mở rộng trong JDK 25

JEP 507 bao phủ một số ngữ cảnh:

| Ngữ cảnh | Khả năng được preview |
|---|---|
| Type patterns | Dùng kiểu nguyên thủy như `byte`, `int`, `long`, `float`, `double`, `boolean`, `char` trong pattern |
| `instanceof` | Kiểm tra chuyển đổi chính xác giữa primitive với primitive, hoặc từ reference sang primitive qua các chuyển đổi được cho phép |
| `switch` selector | Dùng mọi kiểu nguyên thủy và wrapper tương ứng làm selector |
| `switch` patterns | Dùng primitive type patterns trong các nhánh `case` |
| Record patterns | Dùng primitive type patterns ở thành phần record |
| `when` guard | Kết hợp pattern với điều kiện bổ sung |

Cần phân biệt hai điểm:

- **Primitive type pattern** kiểm tra một giá trị có thể chuyển đổi chính xác sang kiểu đích hay không và khai báo biến pattern với kiểu đó.
- **Primitive selector/constant trong `switch`** mở rộng những kiểu giá trị mà `switch` có thể nhận, chẳng hạn `long`, `float`, `double` và `boolean`.

`when` là cú pháp guard đã có trong pattern matching. JEP 507 mở rộng kiểu có thể dùng trong pattern; không nên hiểu toàn bộ cơ chế guard là một tính năng mới riêng của JEP này.


## 4. Quy tắc cốt lõi: testing conversion phải chính xác

Một *testing conversion* có thể hợp lệ về mặt kiểu nhưng vẫn không chính xác với một giá trị cụ thể. Ví dụ, Java có thể kiểm tra chuyển đổi từ `int` sang `byte`, nhưng không phải mọi giá trị `int` đều nằm trong miền `byte`.

Một testing conversion được xem là **exact** nếu:

- Không làm mất thông tin số.
- Không gây lỗi trong các bước chuyển đổi như unboxing.
- Giá trị sau chuyển đổi giữ nguyên ý nghĩa số theo quy tắc của JLS.

Ví dụ:

| Chuyển đổi | Giá trị nguồn | Kết quả kiểm tra | Lý do |
|---|---:|---|---|
| `int` → `byte` | `10` | Khớp | Giá trị nằm trong miền byte |
| `int` → `byte` | `1000` | Không khớp | Ép kiểu thông thường cho kết quả `-24` |
| `int` → `float` | `16_777_216` | Có thể khớp | Giá trị biểu diễn chính xác bằng float |
| `int` → `float` | `16_777_217` | Không khớp | Float không biểu diễn chính xác giá trị này |
| `double` → `int` | `42.0` | Khớp | Chuyển đổi giữ nguyên giá trị |
| `double` → `int` | `42.5` | Không khớp | Phần thập phân sẽ bị mất |
| `double` → `int` | `NaN` | Không khớp | Không thể chuyển thành số nguyên mà giữ nguyên giá trị |
| `double` → `int` | `-0.0` | Không khớp | Chuyển thành `0` làm mất dấu âm của zero |

Ví dụ kiểm tra bằng code:

```java
static void checkExactConversions() {
    int exact = 16_777_216;
    int inexact = 16_777_217;

    System.out.println(exact instanceof float f1);   // true
    System.out.println(inexact instanceof float f2); // false

    double whole = 42.0;
    double fraction = 42.5;

    System.out.println(whole instanceof int i);      // true
    System.out.println(fraction instanceof int j);   // false
}
```

Không nên thay logic kiểm tra bằng phép ép kiểu rồi so sánh ngược một cách tùy tiện. Quy tắc exactness của JLS xử lý các trường hợp số dấu phẩy động, `NaN`, infinity và negative zero theo định nghĩa cụ thể; round-trip cast có thể bỏ sót một số trường hợp mất thông tin.



## 5. Dùng primitive type pattern với toán tử instanceof

### 5.1. Kiểm tra narrowing conversion an toàn

Một giá trị `int` có thể được kiểm tra xem có biểu diễn chính xác bằng `byte` hay không:

```java
static String toByteDescription(int value) {
    if (value instanceof byte small) {
        return "byte = " + small;
    }
    return "Không thể chuyển chính xác sang byte";
}
```

Biến `small` chỉ được khởi tạo khi pattern khớp. Nếu phép chuyển đổi làm mất thông tin, pattern trả về `false` và biến pattern không được sử dụng.

Cách viết này hữu ích khi cần kiểm tra một miền số và đồng thời lấy giá trị đã chuyển đổi. Tuy nhiên, do tính năng đã bị rút khỏi lộ trình, mã production mới nên tiếp tục dùng kiểm tra giới hạn tường minh hoặc một hàm chuyển đổi ổn định.

### 5.2. Kiểm tra giá trị wrapper và unboxing

Primitive patterns cũng có thể kiểm tra một reference value thông qua các chuyển đổi reference và unboxing được phép:

```java
static String fromObject(Object candidate) {
    if (candidate instanceof int value) {
        return "Giá trị Integer có thể unbox thành int: " + value;
    }
    return "Không khớp với int";
}
```

Với `candidate = Integer.valueOf(42)`, pattern khớp. Với `null`, pattern không khớp; nó không thực hiện unboxing một giá trị null rồi ném `NullPointerException`.

**Kiểu tĩnh của biểu thức cũng quan trọng.** Ví dụ JLS dùng `List<Short>`:

```java
List<Short> values = List.of((short) 12);

if (values.get(0) instanceof int number) {
    System.out.println(number); // 12
}
```

Ở đây kiểu tĩnh của `values.get(0)` là `Short`, nên phép kiểm tra có thể unbox `short` rồi widening sang `int`. Nếu chỉ giữ giá trị đó dưới kiểu tĩnh `Object`, quy tắc kiểm tra sẽ khác vì compiler phải xét các testing conversion hợp lệ từ `Object`.

Không suy luận rằng mọi wrapper number đều có thể chuyển sang mọi primitive target. Chuyển đổi phải hợp lệ theo kiểu tĩnh và phải chính xác ở runtime.

### 5.3. Kiểm tra primitive type mà không khai báo biến

Preview cũng mở rộng toán tử type comparison:

```java
int value = 1000;

if (value instanceof byte) {
    System.out.println("Có thể biểu diễn chính xác bằng byte");
} else {
    System.out.println("Không thể biểu diễn chính xác bằng byte");
}
```

Dạng có pattern variable thường hữu ích hơn khi cần dùng giá trị sau kiểm tra. Dạng type comparison phù hợp khi chỉ cần câu trả lời boolean.



## 6. Mở rộng switch sang mọi primitive type

Trước đây, `switch` có giới hạn về selector type. JEP 507 mở rộng selector để hỗ trợ các primitive types, bao gồm `long`, `float`, `double` và `boolean`, cùng wrapper tương ứng.

Ví dụ với `boolean`:

```java
static String describe(boolean enabled) {
    return switch (enabled) {
        case true -> "Đang bật";
        case false -> "Đang tắt";
    };
}
```

Ví dụ với `long`:

```java
static String classify(long code) {
    return switch (code) {
        case 200L -> "Thành công";
        case 404L -> "Không tìm thấy";
        case 500L -> "Lỗi máy chủ";
        default -> "Mã khác";
    };
}
```

Với `float` và `double`, các case constant phải tuân theo quy tắc tương thích kiểu của selector. Ví dụ:

```java
static String classifyTemperature(double value) {
    return switch (value) {
        case 0.0 -> "Điểm đóng băng";
        case 100.0 -> "Điểm sôi";
        default -> "Nhiệt độ khác";
    };
}
```

Đây là các ví dụ sử dụng preview language feature của Java 25. Không được bỏ `--enable-preview` khi compile hoặc run.



## 7. Kết hợp primitive type patterns trong switch

Primitive type patterns cho phép `switch` kiểm tra một giá trị số theo các kiểu đích khác nhau.

```java
static String classifyDouble(double value) {
    return switch (value) {
        case int intValue -> "Chuyển đổi chính xác sang int: " + intValue;
        case double doubleValue -> "Giá trị double: " + doubleValue;
    };
}
```

Ví dụ:

- `42.0` khớp `int` vì có thể chuyển chính xác thành `42`.
- `42.5` không khớp `int`, nên đi đến `double`.
- Một giá trị nằm ngoài miền `int` cũng không khớp `int`.
- `NaN` vẫn khớp pattern `double`.

Thứ tự pattern có ý nghĩa. Pattern rộng hơn có thể dominate pattern hẹp hơn. Ví dụ pattern `double d` không nên đứng trước pattern `int i` trong switch này, bởi `double` là pattern khớp mọi giá trị của selector `double`; các nhánh sau sẽ bị coi là unreachable.



## 8. Dùng primitive patterns trong record patterns

JEP 507 cho phép primitive type patterns xuất hiện trong component patterns của record.

```java
record Rgb(int red, int green, int blue) {}

static String describe(Rgb color) {
    return switch (color) {
        case null -> "Không có màu";
        case Rgb(byte smallRed, byte smallGreen, byte smallBlue) ->
            "Ba thành phần đều nằm trong miền byte";
        case Rgb(int redValue, int greenValue, int blueValue) ->
            "Màu có ít nhất một thành phần ngoài miền byte";
    };
}
```

Nhánh `Rgb(byte ...)` chỉ khớp khi cả ba component có thể chuyển đổi chính xác sang `byte`. Nhánh `Rgb(int ...)` xử lý các record còn lại. `case null` cần thiết vì một record pattern không khớp giá trị null.

Trong một switch có nhiều record patterns, cần kiểm tra dominance và exhaustiveness. Pattern component rộng hơn đặt trước có thể làm pattern hẹp phía sau bị dominate.



## 9. Kết hợp when guard với primitive pattern

Guard cho phép kiểm tra thêm điều kiện sau khi pattern đã khớp:

```java
static String describeNumber(double value) {
    return switch (value) {
        case double nanValue when Double.isNaN(nanValue) ->
            "Not a Number";
        case double infiniteValue when Double.isInfinite(infiniteValue) ->
            "Infinity";
        case double negativeValue when negativeValue < 0 ->
            "Số âm";
        case double otherValue ->
            "Số không âm hữu hạn";
    };
}
```

Các nhánh đầu dùng cùng một primitive type pattern `double`, sau đó áp dụng guard theo từng trường hợp. Pattern không khớp hoặc guard trả về false thì việc xét switch tiếp tục với label kế tiếp.

Guard phải có kiểu `boolean` hoặc `Boolean`. Nếu guard sử dụng một biến bên ngoài, biến đó phải là `final` hoặc effectively final theo quy tắc của Java.



## 10. Hiểu dominance và exhaustiveness trước khi viết switch

Primitive patterns làm quy tắc dominance phức tạp hơn vì một pattern có thể khớp một tập con giá trị của pattern khác thông qua exact conversion.

Các nguyên tắc cần nhớ:

- Pattern `double d` là unconditional đối với selector kiểu `double`.
- Pattern `int i` trên selector `double` chỉ khớp những giá trị chuyển đổi chính xác sang `int`.
- Pattern rộng hơn đặt trước có thể khiến pattern hẹp phía sau bị dominate.
- Guard có thể khiến pattern không còn unguarded; quy tắc dominance xử lý guarded và unguarded labels khác nhau.
- Switch expression phải exhaustive.
- Với selector reference type, cần xử lý `null` nếu switch expression có thể nhận null; primitive type không có null.

Ví dụ về thứ tự:

```java
static String classify(double value) {
    return switch (value) {
        case int intValue -> "int chính xác";
        case double doubleValue -> "double";
    };
}
```

Đổi thứ tự thành `case double` trước `case int` sẽ khiến nhánh `int` bị pattern rộng hơn chi phối. Đây là lỗi compile-time, không phải nhánh chỉ đơn giản không bao giờ được chạy.

## 11. Bật preview trong JDK 25

Primitive Types in Patterns là **preview language feature**, vì vậy phải bật preview ở cả compile time và runtime.

Kiểm tra toolchain:

```bash
java -version
javac -version
```

Compile bằng JDK 25:

```bash
javac --release 25 --enable-preview -Xlint:preview -d out PrimitivePatternsDemo.java
```

Chạy bằng cùng JDK 25:

```bash
java --enable-preview -cp out PrimitivePatternsDemo
```

Ý nghĩa:

| Tùy chọn | Mục đích |
|---|---|
| `--release 25` | Biên dịch theo Java SE 25 |
| `--enable-preview` | Cho phép compiler sử dụng preview language features của JDK 25 |
| `-Xlint:preview` | Hiển thị cảnh báo liên quan đến việc dùng preview |
| `-d out` | Ghi class files vào thư mục `out` |

**Không bật preview chỉ ở một phía.** Nếu compile không có `--enable-preview`, source sử dụng primitive patterns sẽ bị từ chối. Nếu compile có preview nhưng runtime không bật `--enable-preview`, JVM sẽ từ chối load class file phụ thuộc preview.

`--enable-preview` áp dụng cho toàn bộ preview features của release đang dùng. Không có tùy chọn chỉ bật riêng JEP 507.

Trong project nhiều module, module chứa source dùng preview phải được compile với đúng JDK và preview flag. Test runner hoặc process được fork để chạy test cũng phải có runtime flag. Không phát hành thư viện chứa class files preview cho downstream mà không kiểm soát được JDK/runtime của họ.



## 12. Preview class file bị ràng buộc với đúng JDK release

Class file được biên dịch từ preview language feature mang dấu hiệu phụ thuộc preview của release tương ứng. Theo JVM Specification, class file này chỉ được load khi:

1. Runtime là đúng Java SE release mà class file phụ thuộc.
2. Preview features của release đó được bật.

Class file preview của Java 25 **không thể được load trên JDK 26 hoặc JDK 27**, kể cả khi các runtime mới hơn cũng bật `--enable-preview`. Preview feature có thể thay đổi giữa các release, vì vậy bytecode không được coi là artifact tương thích xuyên phiên bản.

Đây là một rủi ro quan trọng khi đưa code preview vào thư viện:

- Downstream phải chạy đúng JDK release.
- Runtime phải bật preview.
- Nâng JDK đòi hỏi biên dịch lại và kiểm tra source.
- Preview có thể đổi quy tắc, trở thành final hoặc bị rút khỏi release sau.

Không coi `--release 25` là cách làm preview trở thành ổn định. Nó chỉ khóa API/source target ở Java 25; nó không xóa phụ thuộc preview khỏi class file.



## 13. Lịch sử preview và trạng thái mới nhất

| JDK | JEP | Trạng thái |
|---|---|---|
| 23 | JEP 455 | Preview lần đầu |
| 24 | JEP 488 | Preview lần thứ hai |
| 25 | JEP 507 | Preview lần thứ ba |
| 26 | JEP 530 | Preview lần thứ tư; cập nhật exactness và dominance |
| 27 | JEP 532 | Preview lần thứ năm |
| 28 | — | Dự kiến loại bỏ tính năng; không thể bật bằng `--enable-preview` |

Ngày 11/11/2026, nhóm Java thông báo dừng phát triển Primitive Types in Patterns, `instanceof`, and `switch`. Draft JEP cho preview lần thứ sáu được rút. Lý do được nêu là quy tắc exact numeric conversion hiện tại cần được xem xét trong bối cảnh Project Valhalla đang phát triển hướng mới cho Java numerics, có thể gồm user-defined numeric types.

Nhóm ngôn ngữ Java dự định nghiên cứu một tính năng khác tên **Constant Patterns**, có thể tiếp tục một phần công việc về primitive support trong `switch`. Đây là hướng thiết kế được thông báo, không phải tính năng đã được phát hành hoặc một thay thế tương thích để sử dụng ngay.

**Quyết định cho dự án mới:** không chọn Primitive Types in Patterns làm nền tảng cú pháp cho code dùng chung. Chỉ giữ ví dụ trong môi trường học tập hoặc project bị pin vào JDK 25 để hiểu lịch sử thiết kế, kiểm tra mã cũ và đánh giá tác động migration.



## 14. Khi nào có thể thử và khi nào nên tránh?

| Bối cảnh | Quyết định | Lý do |
|---|---|---|
| Bài học hoặc prototype cô lập trên JDK 25 | Có thể thử | Mục tiêu là hiểu cú pháp và thu thập kinh nghiệm |
| Đọc hoặc duy trì ứng dụng đã pin JDK 25 preview | Có thể giữ tạm trong phạm vi kiểm soát | Cần đúng JDK 25 và runtime flag |
| Thư viện công khai hoặc dependency dùng chung | Tránh | Class file preview buộc downstream vào đúng release |
| Dịch vụ cần nâng JDK thường xuyên | Tránh | Source có thể không biên dịch trên release tiếp theo |
| Project mới nhắm JDK 26/27 | Không nên bắt đầu | Tính năng đã ngừng phát triển dù các release này từng có preview |
| Project chuẩn bị nâng lên JDK 28 | Phải loại bỏ | JDK 28 dự kiến không còn tính năng, kể cả khi bật preview |

Preview vốn được cung cấp để nhận phản hồi thực tế. Việc một feature có mặt trong nhiều preview release không phải cam kết rằng nó sẽ trở thành final. Trường hợp này đã được nhóm Java chính thức rút khỏi lộ trình, nên mức rủi ro cao hơn một preview vẫn đang được phát triển.



## 15. Cách viết ổn định thay thế cho mã dùng chung

Khi cần chuyển đổi `int` sang `byte` an toàn, dùng kiểm tra miền tường minh:

```java
static Optional<Byte> toByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        return Optional.empty();
    }
    return Optional.of((byte) value);
}
```

Khi cần kiểm tra wrapper type, dùng reference pattern đã ổn định:

```java
static String describe(Object value) {
    if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    if (value instanceof Long number) {
        return "Long: " + number;
    }
    return "Kiểu khác";
}
```

Khi cần phân loại một số thực, có thể viết điều kiện tường minh theo yêu cầu nghiệp vụ:

```java
static String classifyStable(double value) {
    if (Double.isNaN(value)) {
        return "NaN";
    }
    if (Double.isInfinite(value)) {
        return "Infinity";
    }
    if (value < 0) {
        return "Số âm";
    }
    return "Số không âm hữu hạn";
}
```

Với selector `long`, `float`, `double` hoặc `boolean`, nếu không muốn phụ thuộc preview, dùng `if/else` hoặc chuẩn hóa giá trị thành enum/reference type rồi xử lý bằng switch ổn định. Switch constants truyền thống cho các kiểu đã được hỗ trợ từ trước vẫn dùng được; phần mở rộng preview nằm ở các selector, constants và patterns mới của JEP 507.

Các cách viết ổn định có thể dài hơn primitive patterns, nhưng không phụ thuộc preview và có thể được biên dịch/chạy trên các JDK mục tiêu ổn định.



## 16. Quy trình đánh giá một codebase đã dùng JEP 507

Nếu một project hiện có primitive patterns được biên dịch bằng Java 25 preview, hãy kiểm tra trước khi nâng JDK:

1. Tìm các biểu thức `instanceof` có primitive target, ví dụ `instanceof int`, `instanceof byte`.
2. Tìm `switch` có selector `long`, `float`, `double`, `boolean` hoặc wrapper tương ứng.
3. Tìm primitive type patterns trong `case` labels.
4. Tìm primitive patterns lồng trong record patterns.
5. Ghi nhận các guard `when` và thứ tự pattern có thể bị ảnh hưởng bởi dominance.
6. Xác định module/library nào đang phát hành class files phụ thuộc preview.
7. Thay primitive patterns bằng kiểm tra miền, reference patterns và logic chuyển đổi ổn định.
8. Biên dịch lại trên JDK mục tiêu mà không bật preview.
9. Chạy unit tests cho giá trị biên, giá trị mất chính xác, wrapper, null, NaN và infinity.
10. Kiểm tra artifact downstream không còn class file phụ thuộc preview.

Đặc biệt, đừng chỉ thay compiler flag hoặc nâng `--release` rồi kỳ vọng source cũ vẫn biên dịch. JDK 28 dự kiến không còn tính năng này ngay cả khi bật preview.



## 17. Bài thực hành: thử nghiệm có kiểm soát trên JDK 25

Tạo file `PrimitivePatternsDemo.java`:

```java
import java.util.Optional;

public class PrimitivePatternsDemo {

    record Point(int x, int y) {}

    static String narrow(int value) {
        if (value instanceof byte small) {
            return "byte=" + small;
        }
        return "int=" + value;
    }

    static String classify(double value) {
        return switch (value) {
            case int intValue -> "exact int=" + intValue;
            case double doubleValue -> "double=" + doubleValue;
        };
    }

    static String describe(Object candidate) {
        if (candidate instanceof int number) {
            return "Integer value=" + number;
        }
        return "not matched as int";
    }

    static String describePoint(Point point) {
        return switch (point) {
            case null -> "null";
            case Point(byte smallX, byte smallY) -> "small point";
            case Point(int xValue, int yValue) -> "general point";
        };
    }

    static Optional<Byte> stableAlternative(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            return Optional.empty();
        }
        return Optional.of((byte) value);
    }

    public static void main(String[] args) {
        System.out.println(narrow(10));
        System.out.println(narrow(1000));

        System.out.println(classify(42.0));
        System.out.println(classify(42.5));

        System.out.println(describe(Integer.valueOf(12)));
        System.out.println(describe(Short.valueOf((short) 12)));
        System.out.println(describe(null));

        System.out.println(describePoint(new Point(10, 20)));
        System.out.println(describePoint(new Point(1000, 20)));
        System.out.println(describePoint(null));

        System.out.println(stableAlternative(10));
        System.out.println(stableAlternative(1000));
    }
}
```

Biên dịch và chạy trên JDK 25:

```bash
javac --release 25 --enable-preview -Xlint:preview -d out PrimitivePatternsDemo.java
java --enable-preview -cp out PrimitivePatternsDemo
```

Quan sát:

- `narrow(10)` khớp `byte`; `narrow(1000)` không khớp.
- `classify(42.0)` khớp `int`; `classify(42.5)` rơi về `double`.
- `Integer` có thể được kiểm tra theo `int`; `Short` được truyền qua tham số kiểu `Object` không tự động khớp `int`. Kiểu tĩnh của biểu thức ảnh hưởng đến testing conversion.
- `Point(byte, byte)` chỉ khớp khi cả hai component chuyển đổi chính xác; các giá trị còn lại khớp `Point(int, int)`.
- `stableAlternative` cho thấy cách thay thế không cần preview.

Đây là bài thực hành trên toolchain Java 25 được pin cố định, không phải khuyến nghị đưa preview vào production.



## 18. Checklist trước khi bật preview

- [ ] Xác nhận đúng JDK 25 và đúng vendor/build có hỗ trợ JEP 507.
- [ ] Hiểu Primitive Types in Patterns là preview lần thứ ba, chưa phải tính năng final.
- [ ] Đọc trạng thái mới nhất: nhóm Java đã dừng phát triển và dự kiến loại bỏ tính năng khỏi JDK 28.
- [ ] Chỉ thử nghiệm trong project cô lập, không đưa vào API/library dùng chung mới.
- [ ] Dùng `javac --release 25 --enable-preview` để compile.
- [ ] Dùng `java --enable-preview` để run bằng cùng JDK 25.
- [ ] Dùng `-Xlint:preview` để nhìn rõ cảnh báo.
- [ ] Không giả định class file preview Java 25 có thể chạy trên JDK 26/27.
- [ ] Kiểm tra exact conversion với giá trị biên và giá trị mất precision.
- [ ] Kiểm tra wrapper, unboxing, null, `NaN`, infinity và negative zero.
- [ ] Kiểm tra dominance và exhaustiveness của switch.
- [ ] Có phương án thay thế ổn định trước khi nâng JDK.
- [ ] Không dùng `--enable-preview` như cách khôi phục tính năng trên JDK 28.

### Tài liệu tham khảo chính thức

1. [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507)
2. [Oracle Java SE 25 — Primitive types in patterns, instanceof, and switch (Third Preview JLS)](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
3. [Oracle Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html)
4. [Oracle Java SE 25 — JVM Specification, Preview Features](https://docs.oracle.com/javase/specs/jvms/se25/jvms25.pdf)
5. [JEP 12 — Preview Language and VM Features](https://openjdk.org/jeps/12)
6. [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview, JDK 26)](https://openjdk.org/jeps/530)
7. [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview, JDK 27)](https://openjdk.org/jeps/532)
8. [Inside.java — Withdrawing the Primitive Patterns Preview Feature (11 November 2026)](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/)
9. [OpenJDK Amber Spec Experts — Withdrawing the Primitive Patterns preview feature](https://mail-archive.com/amber-spec-experts%40openjdk.org/msg00923.html)
