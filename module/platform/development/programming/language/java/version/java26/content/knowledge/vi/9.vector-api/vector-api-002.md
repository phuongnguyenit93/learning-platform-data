# Phần thực hành dùng module và API incubator Java 27

Java 27 tiếp tục cung cấp Vector API dưới dạng **Twelfth Incubator** theo JEP 537, trong module JDK `jdk.incubator.vector` và package `jdk.incubator.vector`. API biểu diễn phép tính trên nhiều phần tử cùng lúc bằng các vector có nhiều lane. HotSpot JIT có thể biên dịch những phép toán này thành lệnh SIMD phù hợp với CPU đang chạy, chẳng hạn AVX trên x64 hoặc NEON trên AArch64. Nếu runtime không thể dùng lệnh vector cho một phép toán hoặc shape đã chọn, API có implementation scalar để vẫn thực hiện được phép tính.

Đây là **incubator API**, không phải Java SE API ổn định và cũng không phải preview feature. Khi dùng ứng dụng classpath, phải thêm module bằng `--add-modules jdk.incubator.vector` ở cả compile và run. Không dùng `--enable-preview` để bật module này. JDK 27 tiếp tục lần incubator thứ mười hai; JEP 537 không đưa ra thay đổi triển khai đáng kể so với các vòng gần trước đó, nhưng API vẫn có thể thay đổi hoặc bị rút lại ở release sau. [JEP 537](https://openjdk.org/jeps/537) · [JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) · [Module `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

## 1. Vector API giải quyết bài toán nào?

Với vòng lặp scalar, mỗi lần lặp xử lý một phần tử:

```java
for (int i = 0; i < a.length; i++) {
    c[i] = a[i] * b[i];
}
```

Với Vector API, một vector chứa nhiều giá trị cùng kiểu nguyên thủy. Một phép `mul` áp dụng phép nhân cho tất cả lane tương ứng trong một biểu thức Java:

```java
FloatVector va = FloatVector.fromArray(SPECIES, a, offset);
FloatVector vb = FloatVector.fromArray(SPECIES, b, offset);
FloatVector vc = va.mul(vb);
vc.intoArray(c, offset);
```

Nếu species có 8 lane, một lần `mul` biểu diễn 8 phép nhân float độc lập. Runtime có thể ánh xạ phép toán này thành một hoặc nhiều lệnh SIMD của CPU. Số lane thực tế phụ thuộc element type và vector shape được chọn trên nền tảng.

Vector API hữu ích với các workload có nhiều phép tính số học độc lập trên mảng hoặc dữ liệu liên tục, ví dụ xử lý ảnh, tín hiệu, ma trận, mô phỏng, thống kê và một số phép tính khoa học. API không tự biến mọi vòng lặp Java thành vector; lập trình viên biểu diễn phép tính theo vector để JIT có thể tối ưu hóa nó.

### Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa | API thường dùng |
|---|---|---|
| **Lane** | Một vị trí chứa một giá trị nguyên thủy trong vector. | `Vector.length()`, `lane(i)` |
| **Element type** | Kiểu dữ liệu của mỗi lane: `byte`, `short`, `int`, `long`, `float` hoặc `double`. | `IntVector`, `FloatVector`, `DoubleVector`... |
| **Vector shape** | Kích thước vector theo bit, ví dụ 128, 256 hoặc 512 bit. | `VectorShape` |
| **Vector species** | Tổ hợp element type và shape; xác định kiểu và số lane của vector. | `VectorSpecies`, `FloatVector.SPECIES_PREFERRED` |
| **Lane-wise operation** | Phép toán được áp dụng độc lập lên từng lane tương ứng. | `add`, `sub`, `mul`, `div`, `compare` |
| **Vector mask** | Tập cờ boolean xác định lane nào được đọc, ghi hoặc tham gia phép toán. | `VectorMask`, `indexInRange` |
| **Vector shuffle** | Sắp xếp hoặc di chuyển lane giữa các vector. | `VectorShuffle`, `rearrange`, `slice` |
| **Reduction** | Gộp nhiều lane thành một giá trị scalar. | `reduceLanes(VectorOperators.ADD)` |

Một vector có element type `float` và shape 256 bit chứa 8 lane vì mỗi float chiếm 32 bit. Không được giả định mọi CPU đều hỗ trợ mọi shape. Nên bắt đầu từ species được runtime khuyến nghị thay vì cố định `SPECIES_512` hoặc một chiều rộng phần cứng cụ thể.

## 2. Chọn species phù hợp với máy đang chạy

`VectorSpecies<E>` quản lý các vector có cùng element type và shape. Với mỗi kiểu vector, API cung cấp hằng `SPECIES_PREFERRED`. Ví dụ:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Float> SPECIES = FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` chọn species có kích thước vector được ưu tiên trên nền tảng hiện tại. `SPECIES.length()` trả về số lane của vector đó. Cách chọn này giúp code thích ứng với CPU có vector width khác nhau mà không cần tự phát hiện AVX, NEON hoặc SVE.

API cũng có các species cố định như `SPECIES_128`, `SPECIES_256`, `SPECIES_512` và `SPECIES_MAX`. Chỉ chọn shape cố định khi thuật toán hoặc giao thức dữ liệu thực sự yêu cầu nó và đã kiểm tra khả năng hỗ trợ trên mọi môi trường đích. Nếu shape không được phần cứng hỗ trợ, runtime có thể dùng implementation scalar; việc chọn vector lớn hơn không tự động làm chương trình nhanh hơn.

Javadoc khuyến nghị lưu species trong biến cục bộ, tham số hoặc trường `static final`. Tránh lưu các object vector, mask hoặc species trong các field thông thường hay phần tử mảng nếu không cần thiết; dù hợp lệ về ngữ nghĩa, cách lưu đó có thể gây bất lợi cho tối ưu của JIT.

## 3. Bật module incubator trên classpath

Giả sử source file là `src/VectorMultiply.java` và class không khai báo package. Dùng `javac` của JDK 27 để biên dịch:

```bash
javac --release 27 --add-modules jdk.incubator.vector -d out src/VectorMultiply.java
```

Khi chạy, phải thêm module vào tập module được resolve:

```bash
java --add-modules jdk.incubator.vector -cp out VectorMultiply
```

`--add-modules` yêu cầu module system resolve module incubator để code trên classpath có thể đọc package `jdk.incubator.vector`. Nếu bỏ cờ này, chương trình có thể không tìm thấy module hoặc package khi compile/run.

Compiler và launcher có thể in cảnh báo cho biết đang dùng incubator module, ví dụ `using incubating module(s): jdk.incubator.vector`. Đây là cảnh báo trạng thái API, không phải lỗi biên dịch. Không nên tắt cảnh báo chỉ để che giấu rủi ro phụ thuộc vào API chưa ổn định.

Hai cơ chế sau có mục đích khác nhau:

| Cơ chế | Dùng cho | Cờ cần nhớ |
|---|---|---|
| Preview feature | Tính năng ngôn ngữ hoặc API preview trong release cụ thể. | `--enable-preview` ở compile và run, với đúng JDK release. |
| Incubator module | API thử nghiệm được đóng gói thành module JDK riêng. | `--add-modules jdk.incubator.vector` khi module chưa được resolve; module descriptor có thể khai báo `requires`. |

Vector API Java 27 thuộc nhóm thứ hai. `--enable-preview` không thay thế `--add-modules` và không làm module incubator trở thành API ổn định.

## 4. Khai báo dependency trong ứng dụng modular

Nếu ứng dụng dùng Java Platform Module System, khai báo module incubator trong `module-info.java`:

```java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
```

Ví dụ cấu trúc source:

```text
src/
└── com.example.vectorapp/
    ├── module-info.java
    └── com/example/vectorapp/VectorMultiply.java
```

Biên dịch module:

```bash
javac --release 27 --module-source-path src -d out -m com.example.vectorapp
```

Chạy module:

```bash
java --module-path out -m com.example.vectorapp/com.example.vectorapp.VectorMultiply
```

Khi module ứng dụng khai báo `requires jdk.incubator.vector`, module system resolve dependency đó theo module graph. Không cần thêm `--add-modules` cho dependency đã được khai báo trong module descriptor. Nếu ứng dụng xuất public API có tham chiếu kiểu `Vector`, `FloatVector` hoặc `VectorSpecies`, dependency incubator sẽ trở thành một phần hợp đồng công khai của ứng dụng; nên giữ các kiểu incubator bên trong implementation khi có thể để giảm ảnh hưởng tới module tiêu thụ.

## 5. Thực hành: nhân hai mảng float bằng Vector API

Bài tập dùng hai mảng đầu vào cùng kích thước và ghi kết quả vào mảng thứ ba. Vòng lặp vector xử lý các block đầy đủ; vòng lặp scalar xử lý phần tử còn dư.

```java
import java.util.Arrays;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorMultiply {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Arrays must have the same length");
        }

        int upperBound = SPECIES.loopBound(a.length);
        int i = 0;

        // Mỗi vòng xử lý trọn một vector.
        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            FloatVector vc = va.mul(vb);
            vc.intoArray(result, i);
        }

        // Xử lý các phần tử còn lại không đủ một vector.
        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }

    public static void main(String[] args) {
        float[] a = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f};
        float[] b = {2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
        float[] result = new float[a.length];

        multiply(a, b, result);

        System.out.println("lanes per vector: " + SPECIES.length());
        System.out.println(Arrays.toString(result));
    }
}
```

`SPECIES.loopBound(a.length)` trả về chỉ số lớn nhất không vượt quá độ dài mảng và là bội số của số lane. Vì thế, mỗi lần gọi `fromArray` và `intoArray` trong vòng vector đều truy cập đủ số phần tử. Vòng scalar cuối xử lý phần đuôi có độ dài nhỏ hơn `SPECIES.length()`.

Ví dụ có thể chạy với JDK 27 bằng hai lệnh ở phần classpath. Nếu `SPECIES.length()` lớn hơn số phần tử trong mảng, vòng vector không chạy và toàn bộ dữ liệu được xử lý bởi vòng scalar. Nếu độ dài mảng là bội số của số lane, vòng scalar không cần xử lý phần tử nào.

## 6. Xử lý phần đuôi bằng `VectorMask`

Thay vì tách vòng scalar, có thể dùng mask để đánh dấu các lane nằm trong giới hạn mảng. `VectorSpecies.indexInRange(offset, limit)` tạo mask với lane hợp lệ bật và lane vượt giới hạn tắt.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Float> SPECIES = FloatVector.SPECIES_PREFERRED;

static void multiplyMasked(float[] a, float[] b, float[] result) {
    if (a.length != b.length || a.length != result.length) {
        throw new IllegalArgumentException("Arrays must have the same length");
    }

    for (int i = 0; i < a.length; i += SPECIES.length()) {
        VectorMask<Float> mask = SPECIES.indexInRange(i, a.length);
        FloatVector va = FloatVector.fromArray(SPECIES, a, i, mask);
        FloatVector vb = FloatVector.fromArray(SPECIES, b, i, mask);
        va.mul(vb).intoArray(result, i, mask);
    }
}
```

Khi load, lane không được bật trong mask nhận giá trị mặc định của kiểu (`0.0f` đối với float). Khi store, lane không được bật không ghi ra mảng. Các lane bị mask loại bỏ không cần có chỉ số hợp lệ trong mảng, vì vậy đoạn cuối không đọc hoặc ghi vượt biên.

Cách masked loop dễ viết và hữu ích khi mỗi block có điều kiện riêng. Tuy nhiên, Javadoc lưu ý rằng việc tạo và truyền mask ở mọi vòng có thể không đạt hiệu năng tối ưu trên mảng lớn. Với phép toán đơn giản trên dữ liệu liên tục, cách dùng `loopBound` cộng scalar tail thường là điểm bắt đầu tốt để đo hiệu năng.

## 7. Thực hành reduction: tính tích vô hướng

Một ví dụ khác là tích vô hướng (dot product): nhân từng cặp phần tử rồi cộng các tích lại. Phép nhân được vector hóa; `reduceLanes(ADD)` gộp các lane thành một giá trị scalar.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Float> SPECIES = FloatVector.SPECIES_PREFERRED;

static float dot(float[] a, float[] b) {
    if (a.length != b.length) {
        throw new IllegalArgumentException("Arrays must have the same length");
    }

    int upperBound = SPECIES.loopBound(a.length);
    int i = 0;
    FloatVector partial = FloatVector.zero(SPECIES);

    for (; i < upperBound; i += SPECIES.length()) {
        FloatVector va = FloatVector.fromArray(SPECIES, a, i);
        FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
        partial = partial.add(va.mul(vb));
    }

    float sum = partial.reduceLanes(VectorOperators.ADD);

    for (; i < a.length; i++) {
        sum += a[i] * b[i];
    }

    return sum;
}
```

`reduceLanes(VectorOperators.ADD)` cộng các lane trong vector thành một scalar. Với số thực dấu phẩy động, thứ tự cộng có thể khác vòng scalar tuần tự; phép cộng float không có tính kết hợp tuyệt đối do làm tròn. Vì vậy, kết quả dot product vector có thể lệch vài đơn vị cuối so với phiên bản scalar dù cả hai đều đúng theo thứ tự tính toán của mình. Khi kiểm thử, dùng sai số cho phép phù hợp với miền dữ liệu và yêu cầu nghiệp vụ, không mặc định so sánh `==`.

## 8. Các phép toán, mask và shuffle

Vector API cung cấp các nhóm thao tác chính:

- **Arithmetic:** `add`, `sub`, `mul`, `div`, `min`, `max`, `abs` và các phép toán đặc thù cho kiểu vector.
- **Comparison:** `compare(VectorOperators.LT, other)` trả về `VectorMask` để biểu diễn điều kiện theo từng lane.
- **Masked operation:** các overload nhận mask chỉ tác động lên lane được chọn; `blend` chọn dữ liệu giữa hai vector hoặc thay lane được chọn bằng scalar.
- **Reduction:** `reduceLanes` gộp các lane bằng toán tử như `ADD`, `MUL`, `MIN`, `MAX`.
- **Conversion và reinterpretation:** chuyển kiểu lane hoặc nhìn lại dữ liệu theo kiểu lane khác; phải kiểm tra `part`, shape và khả năng mất thông tin.
- **Shuffle và cross-lane:** sắp xếp hoặc di chuyển lane khi thuật toán cần dữ liệu không nằm cùng vị trí tương ứng.

Ví dụ tạo mask cho những lane có giá trị âm và thay chúng bằng `0.0f`:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;

FloatVector values = FloatVector.fromArray(SPECIES, input, offset);
VectorMask<Float> negative = values.compare(VectorOperators.LT, 0.0f);
FloatVector nonNegative = values.blend(0.0f, negative);
```

Đây là phép xử lý theo lane. Khi ghi kết quả ra mảng, vẫn cần kiểm tra giới hạn bằng vòng `loopBound` hoặc mask thích hợp.

## 9. Tính portable, fallback và giới hạn hiệu năng

Vector API hướng tới tính portable ở cấp Java source: code chọn species phù hợp với runtime, không cần tự viết một nhánh riêng cho từng tập lệnh CPU. Tuy nhiên, portable không có nghĩa mọi máy đều sinh cùng mã máy hoặc đạt cùng hiệu năng.

- Runtime cần hỗ trợ và có khả năng biên dịch phép toán vector sang lệnh phần cứng. Nếu không, implementation scalar được dùng.
- Shape cố định có thể không được CPU hỗ trợ. Dùng `SPECIES_PREFERRED` khi không có lý do rõ ràng để cố định shape.
- Vectorization có lợi khi dữ liệu đủ lớn, truy cập tuần tự và phép tính đủ nhiều so với chi phí load/store và điều phối.
- Với mảng nhỏ, nhánh vector, kiểm tra biên và chi phí tạo giá trị có thể khiến phiên bản scalar nhanh hơn.
- Một số phép reduction trên float/double thay đổi thứ tự tính toán và có thể tạo khác biệt làm tròn.
- Vector, mask, shuffle và species là các kiểu value-based. Tránh dùng `==` để so sánh nội dung; không dùng chúng làm monitor hoặc dựa vào object identity.
- Không giả định mỗi phép toán Java tương ứng đúng một lệnh CPU. JIT có thể kết hợp, chia nhỏ hoặc dùng scalar fallback tùy kiến trúc và trạng thái tối ưu hóa.

Không suy ra hiệu năng chỉ từ số lane. Đo với dữ liệu và workload thật, trên từng loại CPU quan trọng, sau khi JVM đã warm up. Dùng JMH hoặc một benchmark harness đúng cách để so sánh phiên bản scalar và vector; tránh đo một lần bằng `System.nanoTime()` rồi kết luận. Theo dõi throughput, latency, allocation, CPU utilization và tính chính xác của kết quả.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `package jdk.incubator.vector does not exist` | Module incubator chưa được resolve lúc biên dịch. | Thêm `--add-modules jdk.incubator.vector` hoặc khai báo `requires jdk.incubator.vector` trong module descriptor. |
| `NoClassDefFoundError` hoặc lỗi không đọc được module khi chạy | Launcher không resolve module incubator cho ứng dụng classpath. | Thêm `--add-modules jdk.incubator.vector` lúc chạy; với named module, kiểm tra `requires`. |
| Cảnh báo incubating module | Compiler/launcher thông báo đang dùng API thử nghiệm. | Đây là cảnh báo trạng thái; ghi nhận rủi ro và theo dõi thay đổi release. |
| `IndexOutOfBoundsException` trong `fromArray` hoặc `intoArray` | Vòng vector đọc/ghi đủ lane khi phần tử cuối không tạo thành vector đầy đủ. | Dùng `loopBound` và scalar tail hoặc dùng mask `indexInRange`. |
| Species không khớp | Hai vector có element type, shape hoặc lane count khác nhau. | Dùng chung species cho các vector tham gia phép toán; kiểm tra bằng `check(species)` khi cần. |
| Không nhanh hơn scalar | Mảng nhỏ, memory-bound, shape không được hỗ trợ hoặc JIT chưa warm up. | Đo lại trên workload đại diện; dùng preferred species và so sánh với baseline scalar đã tối ưu. |
| Kết quả reduction khác phiên bản scalar | Thứ tự cộng/nhân các lane khác nhau và làm tròn float/double. | Xác định sai số cho phép; dùng thuật toán số học phù hợp yêu cầu độ chính xác. |
| Kết quả không ổn định khi lưu vector vào field/mảng | Dựa vào identity hoặc cản trở tối ưu của value-based vector objects. | Giữ vector trong local/parameter; chỉ lưu species trong `static final` khi cần. |

## 11. Tương thích Java 26 và Java 27

Vector API xuất hiện trong nhiều release nhưng vẫn ở incubator: Java 26 là lần thứ mười một (JEP 529), Java 27 là lần thứ mười hai (JEP 537). Module và package vẫn mang tên `jdk.incubator.vector`. JDK 27 không biến API này thành Java SE API, không bỏ yêu cầu resolve module và không cần cờ preview.

Khi nâng từ JDK 26 lên JDK 27:

1. Đổi compile/runtime target sang JDK 27 nếu ứng dụng muốn dùng JDK 27.
2. Giữ `--add-modules jdk.incubator.vector` cho ứng dụng classpath hoặc giữ `requires jdk.incubator.vector` trong module descriptor.
3. Đọc lại Javadoc của JDK 27 để xác nhận chữ ký và hành vi API.
4. Biên dịch lại và chạy benchmark trên CPU mục tiêu; không mang kết luận hiệu năng của JDK/CPU cũ sang runtime mới.
5. Cô lập phần code phụ thuộc Vector API để dễ thay đổi khi API incubator đổi hoặc được thay thế ở release sau.

Vì đây là API incubator, không nên để thư viện công khai phụ thuộc trực tiếp vào `Vector`, `FloatVector` hoặc `VectorSpecies` nếu không kiểm soát được JDK của mọi ứng dụng tiêu thụ. Một thiết kế thực tế là nhận/trả các kiểu Java ổn định như `float[]`, `double[]` hoặc kiểu miền nghiệp vụ, còn phần vector hóa nằm trong implementation nội bộ.

## 12. Checklist trước khi sử dụng

- [ ] Đã xác nhận JDK 27 và trạng thái Vector API là Twelfth Incubator.
- [ ] Đã phân biệt incubator module với preview feature; không dùng `--enable-preview` để bật Vector API.
- [ ] Ứng dụng classpath có `--add-modules jdk.incubator.vector` ở cả compile và run.
- [ ] Ứng dụng modular khai báo `requires jdk.incubator.vector`.
- [ ] Đã dùng `SPECIES_PREFERRED` hoặc xác minh shape cố định được hỗ trợ trên CPU đích.
- [ ] Đã xử lý phần đuôi bằng `loopBound` cộng scalar tail hoặc bằng `VectorMask`.
- [ ] Các vector tham gia cùng phép toán có species tương thích.
- [ ] Đã tránh phụ thuộc vào object identity của vector, mask, shuffle và species.
- [ ] Đã kiểm tra sai số làm tròn khi dùng reduction float/double.
- [ ] Đã đo hiệu năng bằng workload đại diện và so sánh với baseline scalar.
- [ ] Đã cô lập API incubator để có thể sửa khi JDK release sau thay đổi.

## Tài liệu tham khảo chính thức

- [JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [JDK 27 Significant Changes — Vector API](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Java SE 27 — Module `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html)
- [Java SE 27 — Package `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Java SE 27 — `Vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [Java SE 27 — `FloatVector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [Java SE 27 — `VectorSpecies`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [Java SE 27 — `VectorMask`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html)
- [The `javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Java 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

*Cập nhật nội dung: 27-11-2026. Vector API vẫn là incubator module trong JDK 27; kiểm tra Javadoc của JDK mục tiêu và chạy benchmark trên CPU triển khai trước khi quyết định phụ thuộc lâu dài.*
