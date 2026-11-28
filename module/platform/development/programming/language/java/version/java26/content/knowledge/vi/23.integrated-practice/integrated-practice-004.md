# Thử pattern nguyên thủy và Vector bằng cấu hình Java 27 phù hợp

Bài thực hành này ghép hai cơ chế thử nghiệm trong Java 27 vào một luồng xử lý dữ liệu: dùng primitive patterns để kiểm tra và phân loại giá trị số, sau đó dùng Vector API để cộng một mảng `long` theo từng nhóm lane bằng SIMD. Mục tiêu là hiểu đúng cách biên dịch/chạy, xử lý phần tử không khớp và phần đuôi không đủ một vector, rồi so sánh kết quả với cách tính scalar.

Hai tính năng có trạng thái khác nhau:

| Tính năng | Trạng thái trong JDK 27 | Cách bật |
|---|---|---|
| Primitive Types in Patterns, `instanceof`, and `switch` — JEP 532 | Preview language feature lần thứ năm. Cần `--enable-preview` khi biên dịch và chạy. | `--enable-preview` |
| Vector API — JEP 537 | Incubator module lần thứ mười hai, module `jdk.incubator.vector`. | `--add-modules jdk.incubator.vector` |

Java 27 được phát hành ngày 15-09-2026. Tuy nhiên, đến ngày 11-11-2026, nhóm Amber thông báo ngừng phát triển primitive patterns: bản preview thứ sáu bị rút và tính năng sẽ bị loại khỏi JDK 28. Vì vậy, ví dụ primitive patterns dưới đây chỉ dành cho lab trên JDK 27; không dùng nó làm nền tảng cho code production mới hoặc binary dùng chung giữa các release. Vector API vẫn là incubator và cũng chưa phải API ổn định để cam kết lâu dài. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) · [JEP 532](https://openjdk.org/jeps/532) · [Thông báo rút primitive patterns](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/) · [JEP 537](https://openjdk.org/jeps/537).

## 1. Mục tiêu và dữ liệu của bài lab

Ta có một mảng `Object[]` nhận dữ liệu số từ nhiều nguồn. Một số phần tử là `Long`, một số là chuỗi hoặc `null`. Chương trình cần:

1. Chỉ nhận các giá trị có thể khớp primitive pattern `long`.
2. Phân loại giá trị thành âm, nhỏ hơn 100 hoặc từ 100 trở lên bằng primitive pattern trong `switch`.
3. Đưa các giá trị hợp lệ vào `long[]`.
4. Tính tổng bằng Vector API.
5. Tính lại bằng vòng lặp scalar và xác nhận hai kết quả bằng nhau.

```text
Object[] từ nhiều nguồn
        |
        v
primitive instanceof long
        |
        +---- không khớp (String, null, ...)
        |          |
        |          +---- bỏ qua theo quy tắc đầu vào
        |
        +---- khớp, lấy giá trị long
                   |
                   v
             primitive switch
             âm / nhỏ / lớn
                   |
                   v
             long[] liên tục
                   |
          +--------+--------+
          |                 |
          v                 v
      Vector API        scalar loop
          |                 |
          +--------+--------+
                   |
                   v
             so sánh kết quả
```

Đây là bài lab về cú pháp và cách sử dụng API. Không thể kết luận Vector nhanh hơn chỉ từ việc chương trình chạy đúng; hiệu năng còn phụ thuộc CPU, JIT, kích thước dữ liệu, cách cấp phát bộ nhớ và warm-up.

## 2. Primitive patterns trong Java 27

JEP 532 mở rộng pattern matching để primitive types xuất hiện trong các ngữ cảnh pattern. `instanceof` có thể kiểm tra chuyển đổi giữa primitive types và reference types; `switch` có thể nhận mọi primitive type làm selector; các `case` có thể dùng primitive type pattern cùng guard `when`.

Ví dụ kiểm tra một giá trị `Object` có thể chuyển chính xác thành `long`:

```java
static boolean isLongValue(Object candidate) {
    return candidate instanceof long value;
}
```

Khi pattern khớp, biến `value` đã có kiểu primitive `long`. Việc kiểm tra không tương đương với ép kiểu `(long) candidate`: phép ép kiểu có thể ném exception hoặc làm mất thông tin, còn testing conversion của primitive pattern chỉ khớp khi chuyển đổi là chính xác theo quy tắc của JLS.

Primitive patterns còn cho phép kiểm tra một phép thu hẹp có an toàn với giá trị cụ thể hay không:

```java
static Integer toIntIfExact(long value) {
    if (value instanceof int narrowed) {
        return narrowed;
    }
    return null;
}
```

`value instanceof int narrowed` chỉ khớp khi giá trị `long` có thể biểu diễn chính xác bằng `int`. Nếu vượt ngoài `Integer.MIN_VALUE..Integer.MAX_VALUE`, pattern không khớp. Cách này thể hiện ý định kiểm tra rõ ràng hơn việc ép kiểu rồi tự so sánh ngược.

### Primitive pattern khác wrapper pattern

`candidate instanceof Long number` là reference type pattern: biến `number` có kiểu `Long`. `candidate instanceof long number` là primitive type pattern: biến `number` có kiểu `long`, tức đã unbox giá trị.

| Biểu thức | Kiểu biến pattern | Trạng thái |
|---|---|---|
| `value instanceof Long n` | `Long` | Stable từ Java 16. |
| `value instanceof long n` | `long` | Preview trong Java 27, JEP 532. |
| `switch (value) { case Long n -> ... }` | `Long` | Pattern switch stable từ Java 21. |
| `switch (value) { case long n -> ... }` | `long` | Primitive pattern preview trong Java 27. |

Nếu chỉ cần kiểm tra một wrapper cụ thể và lấy giá trị, dùng reference pattern ổn định thường là lựa chọn phù hợp hơn. Primitive pattern hữu ích trong thử nghiệm khi cần diễn đạt trực tiếp phép unboxing hoặc chuyển đổi số có kiểm tra.

## 3. Guard `when` trong primitive `switch`

Primitive selector có thể được phân loại bằng các pattern có guard:

```java
static String classify(long value) {
    return switch (value) {
        case long n when n < 0L -> "negative";
        case long n when n < 100L -> "small";
        case long n -> "large";
    };
}
```

Mỗi `case long n` tạo một pattern variable kiểu `long`. Guard `when` chỉ nhận giá trị khi pattern khớp và biểu thức guard trả về `true`. Nhãn cuối không có guard nên bao phủ các giá trị `long` còn lại, làm switch expression exhaustive.

Thứ tự nhãn có ý nghĩa. Hai nhãn có guard không tự động làm nhãn sau bị dominated vì guard trước có thể trả về `false`. Nếu đưa một pattern không guard lên trước, pattern sau có thể không bao giờ được xét và compiler sẽ báo lỗi dominance.

Primitive patterns cũng không làm `null` trở thành giá trị của primitive. Với `switch` có selector là primitive, giá trị không thể là `null`; với reference selector, cần xử lý `case null` hoặc kiểm tra null trước khi match.

Tài liệu Java 27 mô tả primitive patterns, safe casting, pattern trong record và primitive `switch` tại [Primitive Types in Patterns, `instanceof`, and `switch`](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html). JLS preview mô tả các testing conversion và quy tắc dominance tại [JLS 27 — Fifth Preview](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html).

## 4. Vector API và mô hình SIMD

Vector API biểu diễn một dãy lane có cùng kiểu primitive. Một phép toán như `add` được áp dụng đồng thời trên các lane tương ứng. Cách thực thi này được gọi là SIMD — Single Instruction, Multiple Data.

Ví dụ, nếu một vector có bốn lane:

```text
a = [ 10, 20, 30, 40 ]
b = [  1,  2,  3,  4 ]
        a.add(b)
      = [ 11, 22, 33, 44 ]
```

Một lệnh vector có thể thực hiện nhiều phép cộng lane-wise trên phần cứng hỗ trợ. Vector API không tự tạo nhiều Java thread; nó khai thác vector register và instruction SIMD của CPU. Trên nền tảng không có hỗ trợ SIMD chuyên biệt, chương trình vẫn phải cho kết quả đúng nhưng có thể không có lợi ích hiệu năng.

Các khái niệm cần nắm:

- **Lane:** một phần tử primitive trong vector.
- **Vector length:** số lane của vector.
- **Vector shape:** kích thước vector theo bit.
- **Species:** kết hợp element type và shape; quyết định vector có bao nhiêu lane.
- **Mask:** chọn lane nào tham gia một phép toán hoặc thao tác nạp/lưu.
- **Preferred species:** species phù hợp nhất mà runtime hiện tại đề xuất cho kiểu phần tử đó.

Không hard-code giả định rằng mọi CPU có cùng số lane. Hãy lấy `LongVector.SPECIES_PREFERRED` hoặc species phù hợp khác và dùng nhất quán trong vòng lặp.

```java
private static final VectorSpecies<Long> SPECIES =
        LongVector.SPECIES_PREFERRED;
```

Javadoc của Vector API khuyến nghị truy vấn shape được hỗ trợ trên platform và giữ các phép toán shape-invariant. Các vector tham gia phép toán lane-wise thông thường phải có cùng species. [Java 27 `Vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html) · [Java 27 `LongVector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/LongVector.html).

## 5. Tính tổng bằng vector và xử lý phần đuôi

Vector có số lane cố định. Nếu mảng không chia hết cho số lane, vòng lặp vector không được nạp vượt cuối mảng. Có hai cách phổ biến:

1. Chạy vector trên phần mảng có đủ một vector, rồi xử lý phần còn lại bằng scalar loop.
2. Dùng masked load để chỉ nạp các lane nằm trong phạm vi hợp lệ.

Ví dụ dưới đây dùng cách đầu để dễ kiểm tra:

```java
import jdk.incubator.vector.LongVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

final class VectorSum {
    private static final VectorSpecies<Long> SPECIES =
            LongVector.SPECIES_PREFERRED;

    static long sum(long[] values, int length) {
        int upperBound = length - length % SPECIES.length();
        int i = 0;

        LongVector accumulator = LongVector.zero(SPECIES);

        for (; i < upperBound; i += SPECIES.length()) {
            LongVector chunk = LongVector.fromArray(SPECIES, values, i);
            accumulator = accumulator.add(chunk);
        }

        long total = accumulator.reduceLanes(VectorOperators.ADD);

        // Xử lý các phần tử không đủ một vector.
        for (; i < length; i++) {
            total += values[i];
        }

        return total;
    }
}
```

`upperBound` là bội số lớn nhất của `SPECIES.length()` không vượt quá `length`. Vì vậy, mọi lần `LongVector.fromArray` đều có đủ lane hợp lệ. Sau vòng lặp vector, phần đuôi có ít hơn một vector được cộng bằng scalar.

`reduceLanes(VectorOperators.ADD)` cộng các lane trong vector accumulator thành một giá trị `long`. Sau đó scalar tail được cộng vào tổng. Trong ví dụ này, dữ liệu phải nằm trong miền mà tổng không overflow `long`; phép cộng vector không tự phát hiện overflow số nguyên.

Nếu dùng masked load, có thể tạo mask từ phạm vi mảng và nạp vector cuối cùng mà không đọc ngoài biên. Dù chọn cách nào, phải kiểm tra ranh giới mảng và xác nhận kết quả bằng một implementation scalar độc lập.

## 6. Bài lab tích hợp hoàn chỉnh

Tạo file `PatternVectorLab.java`:

```java
import jdk.incubator.vector.LongVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public class PatternVectorLab {
    private static final VectorSpecies<Long> SPECIES =
            LongVector.SPECIES_PREFERRED;

    static String classify(long value) {
        return switch (value) {
            case long n when n < 0L -> "negative";
            case long n when n < 100L -> "small";
            case long n -> "large";
        };
    }

    static int collectLongValues(Object[] source, long[] destination) {
        int count = 0;

        for (Object candidate : source) {
            if (candidate instanceof long value) {
                destination[count++] = value;
                System.out.printf("%d -> %s%n", value, classify(value));
            }
        }

        return count;
    }

    static long sumScalar(long[] values, int length) {
        long total = 0L;
        for (int i = 0; i < length; i++) {
            total += values[i];
        }
        return total;
    }

    static long sumVector(long[] values, int length) {
        int upperBound = length - length % SPECIES.length();
        int i = 0;
        LongVector accumulator = LongVector.zero(SPECIES);

        for (; i < upperBound; i += SPECIES.length()) {
            LongVector chunk = LongVector.fromArray(SPECIES, values, i);
            accumulator = accumulator.add(chunk);
        }

        long total = accumulator.reduceLanes(VectorOperators.ADD);

        for (; i < length; i++) {
            total += values[i];
        }

        return total;
    }

    public static void main(String[] args) {
        Object[] rawValues = {
                Long.valueOf(12L),
                Long.valueOf(35L),
                Long.valueOf(-7L),
                Long.valueOf(128L),
                "not a number",
                null,
                Long.valueOf(9L)
        };

        long[] accepted = new long[rawValues.length];
        int count = collectLongValues(rawValues, accepted);

        long scalarResult = sumScalar(accepted, count);
        long vectorResult = sumVector(accepted, count);

        if (scalarResult != vectorResult) {
            throw new AssertionError(
                    "Mismatch: scalar=" + scalarResult
                            + ", vector=" + vectorResult);
        }

        System.out.println("Accepted values: " + count);
        System.out.println("Scalar sum: " + scalarResult);
        System.out.println("Vector sum: " + vectorResult);
        System.out.println("Species: " + SPECIES);
        System.out.println("Vector length: " + SPECIES.length());
    }
}
```

Kết quả phân loại của các giá trị số:

| Giá trị | Primitive `instanceof long` | Primitive `switch` |
|---:|---|---|
| `12` | Khớp, lấy `long` | `small` |
| `35` | Khớp, lấy `long` | `small` |
| `-7` | Khớp, lấy `long` | `negative` |
| `128` | Khớp, lấy `long` | `large` |
| `"not a number"` | Không khớp | Không gọi `classify` |
| `null` | Không khớp | Không gọi `classify` |
| `9` | Khớp, lấy `long` | `small` |

Tổng scalar và vector phải giống nhau. Dữ liệu ví dụ có ít phần tử nên thường không cho thấy lợi ích hiệu năng của SIMD; mục tiêu ở đây là kiểm tra luồng xử lý và phần đuôi.

Với dữ liệu mẫu, chương trình nhận 5 giá trị và cả hai cách tính đều trả tổng `177`.

## 7. Cấu hình compiler và runtime Java 27

Hai flag có mục đích độc lập:

- `--enable-preview` bật primitive patterns preview của Java 27.
- `--add-modules jdk.incubator.vector` resolve module incubator chứa Vector API.

Khi một source dùng cả hai, cần cung cấp cả hai flag ở compile time và runtime. Dùng `javac` và `java` từ cùng JDK 27:

```bash
# Kiểm tra đúng JDK trước.
java -version
javac -version

# Compile: preview language feature + incubator module.
javac --release 27 \
      --enable-preview \
      --add-modules jdk.incubator.vector \
      -d out \
      PatternVectorLab.java

# Run: bật preview và resolve Vector API module.
java --enable-preview \
     --add-modules jdk.incubator.vector \
     -cp out \
     PatternVectorLab
```

`--release 27` yêu cầu compiler dùng quy tắc ngôn ngữ, class file target và API của Java 27. `--enable-preview` phải đi cùng `--release 27` khi biên dịch. Runtime cũng phải bật preview. `--add-modules` cần ở cả compile và run vì `jdk.incubator.vector` không được resolve mặc định.

Do source dùng primitive patterns preview, class file được tạo có preview marker của Java 27 (major version `71`, minor version `65535`). Chỉ JVM Java 27 có bật preview mới tải được class file đó. JVM Java 26 hoặc Java 28 không thể dùng `--enable-preview` để mở khóa binary preview này. Vector API tự nó không tạo preview marker; marker xuất hiện vì source đang dùng primitive patterns.

Nếu chỉ thử primitive patterns, bỏ `--add-modules jdk.incubator.vector`. Nếu chỉ thử Vector API, bỏ `--enable-preview` nhưng giữ `--add-modules jdk.incubator.vector`. Không nhầm incubator module với preview feature: bật một flag không tự bật loại tính năng còn lại.

Với project modular, khai báo module dependency trong `module-info.java`:

```java
module com.example.vectorlab {
    requires jdk.incubator.vector;
}
```

Khi compile/run module, module `jdk.incubator.vector` vẫn phải có trong module graph. Với project classpath không có `module-info.java`, dùng `--add-modules` như các lệnh ở trên.

## 8. Kiểm tra các flag và cảnh báo

Vector API là incubator nên compiler/runtime có thể phát cảnh báo rằng chương trình đang sử dụng incubating module. Đây là tín hiệu có chủ đích để người dùng biết dependency chưa ổn định. Không tắt cảnh báo rồi coi API đã trở thành stable.

Các tình huống thường gặp:

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo preview feature bị tắt | Thiếu `--enable-preview` hoặc không dùng `--release 27`. | Dùng JDK 27 và thêm cả hai option khi compile. |
| Runtime báo preview feature chưa bật | Compile có preview nhưng lệnh `java` thiếu flag. | Thêm `--enable-preview` khi chạy bằng JDK 27. |
| `package jdk.incubator.vector is not visible` hoặc module không được resolve | Thiếu `--add-modules jdk.incubator.vector`. | Thêm option khi compile và chạy, hoặc khai báo `requires` trong named module. |
| `NoClassDefFoundError`/`ClassNotFoundException` liên quan Vector API | Runtime không resolve module hoặc chạy bằng JDK không có module phù hợp. | Xác minh `java -version`, module graph và cờ runtime. |
| Preview class không chạy trên JDK khác | Preview class file gắn với release đã biên dịch. | Recompile từ source bằng JDK đích; không tái sử dụng preview binary khác release. |
| Vector code chạy đúng nhưng không nhanh hơn | Mảng nhỏ, CPU không có SIMD phù hợp, JIT chưa warm-up hoặc overhead chiếm ưu thế. | Đo trên workload thực, CPU đích, có warm-up và baseline scalar. |

Có thể kiểm tra module tồn tại trong JDK:

```bash
java --list-modules | findstr jdk.incubator.vector
```

Trên Linux/macOS, dùng `grep` thay `findstr`. Việc module có mặt trong JDK chưa có nghĩa nó đã được resolve vào application module graph.

## 9. Đo hiệu năng đúng cách

Không so sánh một lần chạy scalar với một lần chạy vector bằng `System.nanoTime()` rồi kết luận. JVM cần warm-up; JIT có thể biên dịch lại code; CPU frequency, cache và garbage collection làm kết quả dao động.

Một benchmark có ý nghĩa cần:

1. Dùng dữ liệu đủ lớn và đại diện cho workload thật.
2. Dùng cùng dữ liệu đầu vào cho scalar và vector.
3. Warm-up cả hai implementation trước khi đo.
4. Đo nhiều iteration và báo phân phối/khoảng dao động, không chỉ một con số.
5. Xác nhận kết quả đầu ra giống nhau.
6. Kiểm tra nhiều kích thước mảng, đặc biệt cả trường hợp nhỏ hơn một vector và trường hợp có phần đuôi.
7. Chạy trên CPU và JDK triển khai thực tế; kiểm tra vector species và phần cứng SIMD được hỗ trợ.
8. Dùng JMH hoặc benchmark harness phù hợp thay vì tự viết một vòng đo đơn giản.

Vector API không bảo đảm mọi phép toán đều được vector hóa thành một instruction duy nhất. Truy cập bộ nhớ, nhánh, chuyển đổi dữ liệu và reduction có thể ảnh hưởng kết quả. Nếu phần lớn thời gian nằm ở I/O hoặc object allocation, thay scalar loop bằng vector loop có thể không cải thiện throughput.

Javadoc Java 27 nêu rõ Vector API có thể chạy cả trên platform không có hỗ trợ SIMD chuyên biệt; khi đó không nhất thiết có lợi ích hiệu năng. Implementation hiện được tối ưu chủ yếu cho Intel x64 với AVX2 trở lên và ARM AArch64 với NEON. Kiểm tra giới hạn CPU của môi trường triển khai trước khi chọn API này.

## 10. Phân biệt preview với incubator khi nâng cấp

Hai cơ chế thử nghiệm có lifecycle khác nhau:

| Thuộc tính | Primitive patterns — JEP 532 | Vector API — JEP 537 |
|---|---|---|
| Loại | Preview language feature | Incubator module/API |
| Module | Ngôn ngữ Java; không cần thêm module | `jdk.incubator.vector` |
| Flag chính | `--enable-preview` | `--add-modules jdk.incubator.vector` |
| Compile | JDK 27 + `--release 27 --enable-preview` | JDK 27 + `--add-modules jdk.incubator.vector` |
| Runtime | JDK 27 + `--enable-preview` | Resolve module bằng `--add-modules` |
| Class file | Preview-dependent class file gắn với release | Dùng incubator API không tự nó biến class file thành preview class file |
| Rủi ro | Cú pháp/ngữ nghĩa có thể thay đổi; binary preview không dùng qua release khác | API/module có thể thay đổi hoặc bị loại; cần compile/test lại theo JDK mới |

Tại thời điểm 28-11-2026, primitive patterns vẫn có trong JDK 27 dưới dạng fifth preview. Tuy nhiên, thông báo ngày 11-11-2026 cho biết dự án đã ngừng phát triển, JEP sixth preview bị rút và feature sẽ bị loại khỏi JDK 28. Không dùng primitive patterns trong thư viện dùng chung hoặc sản phẩm cần nâng cấp qua Java 28.

Vector API tiếp tục là incubator ở JDK 27. Việc dùng Vector API không yêu cầu `--enable-preview`; module được resolve bằng `--add-modules`. Cả preview và incubator đều không nên được coi là hợp đồng API ổn định cho dependency production dài hạn.

## 11. Lối viết ổn định thay cho primitive patterns

Nếu cần code có thể duy trì qua các JDK tiếp theo, dùng reference type patterns đã stable và kiểm tra chuyển đổi một cách tường minh:

```java
static String classifyStable(Object value) {
    if (!(value instanceof Long number)) {
        return "unsupported";
    }

    if (number < 0L) {
        return "negative";
    }
    if (number < 100L) {
        return "small";
    }
    return "large";
}
```

`instanceof Long number` là reference pattern stable; không cần `--enable-preview`. Nếu đầu vào có thể là `Integer`, `Short` hoặc `Byte`, xử lý từng wrapper theo hợp đồng dữ liệu hoặc chuẩn hóa tại biên nhận dữ liệu. Đừng dùng ép kiểu số không kiểm tra khi có khả năng mất thông tin.

Với phép cộng, scalar loop là fallback ổn định, không cần incubator module:

```java
static long sumStable(long[] values) {
    long total = 0L;
    for (long value : values) {
        total += value;
    }
    return total;
}
```

Nếu sản phẩm cần độ ổn định API, dùng code scalar và các language feature đã final. Chỉ chuyển sang Vector API khi tổ chức chấp nhận incubator dependency, có benchmark chứng minh lợi ích và có kế hoạch thay đổi khi module tiến triển.

## 12. Bài tập tự kiểm tra

1. Thay `Long` bằng `Integer` trong một phần tử đầu vào. Primitive pattern `instanceof long` có khớp theo kiểu tĩnh và testing conversion không? Viết một test riêng với biến có kiểu `Integer` để phân biệt với biến có kiểu `Object`.
2. Thêm một `long` nằm ngoài miền `int`. Dùng `value instanceof int narrowed` để xác định có thể thu hẹp an toàn hay không.
3. Thêm giá trị `Long.MIN_VALUE`, `Long.MAX_VALUE` và một số âm vào dữ liệu. Xác định miền tổng để tránh overflow.
4. Tạo mảng có độ dài nhỏ hơn `SPECIES.length()`, bằng đúng `SPECIES.length()` và lớn hơn một lane. Xác nhận phần đuôi luôn được xử lý.
5. Thay `LongVector.SPECIES_PREFERRED` bằng species cố định nếu platform hỗ trợ, rồi so sánh số lane và kết quả; không giả định shape cố định là portable.
6. Bỏ `--enable-preview` nhưng giữ `--add-modules`, quan sát lỗi compile/run của primitive patterns.
7. Giữ `--enable-preview` nhưng bỏ `--add-modules`, quan sát lỗi resolve Vector API.
8. Biên dịch code stable ở mục 11 mà không bật preview và không thêm Vector module.
9. Benchmark scalar và vector trên dữ liệu đủ lớn bằng JMH, kiểm tra kết quả và báo cáo CPU/JDK.

## 13. Checklist hoàn thành

- [ ] Đã phân biệt primitive pattern với wrapper/reference pattern.
- [ ] Đã hiểu testing conversion chỉ khớp khi phép chuyển đổi phù hợp và chính xác.
- [ ] Đã dùng `when` guard và bảo đảm switch exhaustive, không bị dominance.
- [ ] Đã biết JEP 532 là fifth preview trong JDK 27 và đã được thông báo rút khỏi JDK 28.
- [ ] Đã dùng `--release 27 --enable-preview` khi biên dịch primitive patterns.
- [ ] Đã dùng `--enable-preview` khi chạy class có preview feature bằng JDK 27.
- [ ] Đã hiểu Vector API là incubator module, không phải preview feature.
- [ ] Đã thêm `--add-modules jdk.incubator.vector` ở compile và runtime.
- [ ] Đã dùng `SPECIES_PREFERRED` thay vì giả định lane count cố định.
- [ ] Đã xử lý vector full chunks và scalar tail hoặc dùng masked load an toàn.
- [ ] Đã so sánh kết quả vector với scalar reference.
- [ ] Đã kiểm tra miền giá trị để tránh overflow.
- [ ] Đã benchmark bằng harness phù hợp trên phần cứng mục tiêu.
- [ ] Đã giữ stable fallback cho code cần chạy lâu dài.
- [ ] Không phát hành dependency preview/incubator như một API production ổn định.

## Tài liệu tham khảo chính thức

- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JEP 532 — Primitive Types in Patterns, `instanceof`, and `switch` (Fifth Preview)](https://openjdk.org/jeps/532)
- [Java SE 27 — Primitive Types in Patterns, `instanceof`, and `switch`](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html)
- [Java SE 27 — Pattern Matching with `switch`](https://docs.oracle.com/en/java/javase/27/language/pattern-matching-switch.html)
- [Java SE 27 — JLS Preview Specification for Primitive Patterns](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Inside Java — Withdrawing the Primitive Patterns Preview Feature (11-11-2026)](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/)
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [Java SE 27 — `Vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [Java SE 27 — `LongVector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/LongVector.html)
- [JDK 27 — `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [JDK 27 — `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)

*Cập nhật nội dung: 28-11-2026. Primitive patterns chỉ dùng thử với JDK 27 và sẽ bị loại khỏi JDK 28 theo thông báo của dự án. Vector API vẫn là incubator module; luôn có stable scalar fallback và kiểm tra lại trạng thái API khi nâng cấp JDK.*
