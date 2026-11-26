# Đánh giá hỗ trợ phần cứng, biên dịch JIT và đường thực thi dự phòng

## 1. Phạm vi và mục tiêu

Bài học thuộc chương **Vector API** trong module Java 22. Mục tiêu là đánh giá một phép tính vector có chạy đúng trên môi trường triển khai, được JIT chuyển thành lệnh SIMD và mang lại lợi ích thực tế hay không.

Java 22 cung cấp vòng incubator thứ bảy của Vector API theo JEP 460; API đã xuất hiện từ các phiên bản Java trước đó. Tại thời điểm đối chiếu **25/11/2026**, tài liệu phát hành JDK 27 vẫn ghi nhận Vector API ở vòng incubator thứ mười hai, JEP 537. Vì vậy, các nguyên tắc về SIMD, chọn species, JIT và fallback vẫn hữu ích ở Java hiện đại; không nên mô tả API này là API đã chuẩn hóa. Nguồn: [Release notes JDK 22](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html), [Release notes JDK 27](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html).

Các ví dụ dùng những API có trong JDK 22: `FloatVector`, `VectorSpecies`, `SPECIES_PREFERRED`, `loopBound` và các phép toán theo lane. Khi chuyển sang JDK mới, cần biên dịch lại và kiểm tra hợp đồng API trên phiên bản đích vì đây vẫn là module incubator.

Sau bài học, bạn có thể:

- Phân biệt khả năng chạy đúng, khả năng sinh lệnh SIMD và hiệu năng của ứng dụng.
- Giải thích ảnh hưởng của CPU, môi trường thực thi và trình biên dịch JIT.
- Thiết kế vòng lặp không cố định số lane và xử lý đúng phần dữ liệu còn dư.
- Phân biệt fallback của thư viện với lựa chọn thuật toán do ứng dụng quản lý.
- Thu thập bằng chứng từ log biên dịch, mã máy và phép đo có kiểm soát.

## 2. “Có hỗ trợ Vector API” gồm những câu hỏi nào?

SIMD, viết đầy đủ là *Single Instruction, Multiple Data*, cho phép một lệnh thực hiện cùng loại phép toán trên nhiều phần tử dữ liệu. Ví dụ, một vector gồm tám lane `float` có thể biểu diễn tám phép nhân độc lập. Các lane không phải tám luồng Java hay tám lõi CPU; Vector API cũng không tự chuyển phép tính sang GPU.

Để đánh giá một môi trường, nên tách bốn câu hỏi sau:

| Câu hỏi | Cần kiểm tra | Kết luận có thể rút ra |
| --- | --- | --- |
| Chương trình có nạp được API không? | Runtime có module `jdk.incubator.vector` và module được resolve | Có thể sử dụng các lớp của API |
| Phép tính có đúng không? | Đầu vào, giới hạn mảng, kiểu phần tử, quy tắc số học | Thuật toán đáp ứng yêu cầu kết quả |
| Kernel có được thực thi bằng SIMD không? | Phép toán, species, trình biên dịch, mã máy sinh ra | Có sử dụng lệnh vector tại đoạn mã quan tâm |
| Ứng dụng có nhanh hơn không? | Benchmark đại diện và đo toàn luồng xử lý | Có lợi ích hiệu năng trong điều kiện đã đo |

**Kernel** ở đây là đoạn tính toán nhỏ được gọi nhiều lần, chẳng hạn biến đổi các phần tử trong một mảng.

Ví dụ, một JVM có thể nạp Vector API và tính đúng toàn bộ kết quả nhưng sử dụng triển khai scalar cho một phép toán. Ngược lại, một kernel có thể chứa lệnh SIMD mà tổng thời gian xử lý request gần như không đổi nếu request chủ yếu chờ cơ sở dữ liệu.

Thiết kế API cho phép thực thi đúng ngay cả khi nền tảng không có phần cứng SIMD chuyên dụng; không thể từ đó suy ra rằng nền tảng ấy sẽ có lợi ích hiệu năng. Nguồn: [Vector — phụ thuộc phần cứng](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html#hardware-platform-dependencies-and-limitations).

## 3. Đánh giá phần cứng và môi trường triển khai

### 3.1. Đánh giá theo tổ hợp, không chỉ theo tên CPU

Đơn vị cần đánh giá là một tổ hợp:

`CPU + hệ điều hành hoặc máy ảo + bản JDK + cấu hình JVM + kiểu dữ liệu + phép toán + species`.

Các họ lệnh AVX trên x64 và NEON trên AArch64 là những ví dụ điển hình về phần cứng SIMD mà Vector API hướng tới. Tuy nhiên, việc tên CPU có một tính năng SIMD không chứng minh rằng mọi phép toán của API đều có ánh xạ phần cứng trực tiếp. Nguồn: [Mô tả module jdk.incubator.vector trong JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html).

Khi lập hồ sơ triển khai, nên ghi lại:

| Thông tin | Lý do cần ghi |
| --- | --- |
| Model CPU và kiến trúc | Hai máy cùng kiến trúc có thể khác tính năng và đặc tính thực thi |
| Hệ điều hành, hypervisor và môi trường container | Môi trường khách có thể được cung cấp tập tính năng CPU hoặc hạn mức tài nguyên khác |
| Nhà cung cấp, phiên bản và build JDK | Cùng mã nguồn có thể được tối ưu khác nhau giữa các build |
| Loại JVM và các cờ khởi chạy | Cờ giới hạn biên dịch hoặc thay đổi tính năng có thể ảnh hưởng kernel |
| Số phần tử, kiểu dữ liệu và cách bố trí dữ liệu | Chi phí thực tế phụ thuộc lượng dữ liệu và cách truy cập |
| Số luồng, giới hạn CPU và tải đồng thời | Kết quả khi chạy đơn lẻ có thể khác tải dịch vụ |

Đây là hồ sơ để tái lập phép đo. Nó không thay thế việc xem mã máy hoặc benchmark.

### 3.2. Chọn species phù hợp

Một `VectorSpecies<Float>` mô tả kiểu phần tử và hình dạng vector. Cách bắt đầu thông dụng là:

```java
private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` biểu diễn lựa chọn ưu tiên của nền tảng. `VectorSpecies.ofPreferred` chọn hình dạng chung hỗ trợ các loại lane; API còn có khái niệm species lớn nhất cho một kiểu phần tử cụ thể. Vì vậy, “preferred” không đồng nghĩa với mọi hình dạng lớn hơn đều không tồn tại. Nguồn: [VectorSpecies.ofPreferred trong JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#ofPreferred(java.lang.Class)).

Với lane `float` có 32 bit, quan hệ kích thước là:

| Kích thước logic của vector | Số lane `float` |
| ---: | ---: |
| 128 bit | 4 |
| 256 bit | 8 |
| 512 bit | 16 |

Bảng này chỉ thể hiện quan hệ giữa số bit và số lane. Nó không cho biết máy của bạn chọn kích thước nào hay tốc độ tăng bao nhiêu lần.

Những hệ quả thực hành:

- Dùng `SPECIES.length()` làm bước nhảy của vòng lặp.
- Dùng `SPECIES.loopBound(n)` xác định phần dữ liệu đủ một vector.
- Không cố định bước nhảy là 8 hoặc 16 chỉ vì máy phát triển hiện tại trả về giá trị đó.
- Giữ species ổn định trong kernel; `static final` giúp thể hiện rõ lựa chọn này.

Không nên mặc định rằng chọn `SPECIES_512` trên máy chỉ tối ưu vector 256 bit sẽ tự được tách thành hai lệnh 256 bit. Phần ghi chú hiệu năng của API mô tả trường hợp hình dạng không phù hợp phải dùng triển khai scalar. Dùng preferred species là điểm xuất phát thích hợp cho mã nguồn cần chạy trên nhiều nền tảng. Nguồn: [Ghi chú hiệu năng của Vector API JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html#performance-notes).

### 3.3. Thông tin species không phải bảng chứng nhận hiệu năng

Những biểu thức sau hữu ích cho chẩn đoán:

```java
System.out.println("VM: " + System.getProperty("java.vm.name"));
System.out.println("JDK: " + Runtime.version());
System.out.println("Arch: " + System.getProperty("os.arch"));
System.out.println("Shape: " + SPECIES.vectorShape());
System.out.println("Bits: " + SPECIES.vectorBitSize());
System.out.println("Lanes: " + SPECIES.length());
```

Nếu thấy `Lanes: 8`, bạn biết cách chia mảng cho species đó. Bạn chưa biết phép toán cụ thể có được intrinsic hóa, kernel đã đủ nóng hay truy cập bộ nhớ có đang chiếm phần lớn thời gian hay không.

Tương tự, kiểm tra `os.arch` bằng chuỗi chỉ cho biết kiến trúc mà JVM báo cáo. Không nên dùng nó làm điều kiện duy nhất để quyết định chạy một kernel cần hiệu năng.

## 4. JIT chuyển phép tính vector thành mã máy như thế nào?

### 4.1. Vai trò của javac và JIT

`javac` biên dịch mã Java thành bytecode. Việc bạn viết `va.mul(scale).add(vb)` không có nghĩa file `.class` đã chứa lệnh AVX hay NEON cố định.

Trong HotSpot thông thường, đoạn mã có thể đi qua thông dịch và các mức biên dịch có thu thập profile trước khi đạt mức tối ưu cao hơn. Cơ chế tiered compilation kết hợp giai đoạn khởi động với việc tối ưu những đoạn được thực thi nhiều. Nguồn: [HotSpot — Tiered Compilation](https://docs.oracle.com/en/java/javase/22/vm/java-hotspot-virtual-machine-performance-enhancements.html#GUID-95603844-3F33-444C-AF3E-22868D3C97F9).

Đối với triển khai HotSpot trong JDK 22, phần xử lý intrinsic của Vector API nằm trong nhánh trình biên dịch tối ưu C2. Mã nguồn kiểm tra theo tổ hợp phép toán, số phần tử và kiểu lane trước khi tạo biểu diễn vector tương ứng. Đây là lý do cần xem xét kernel cụ thể thay vì một cờ “máy hỗ trợ vector” chung. Nguồn: [OpenJDK 22 — vectorIntrinsics.cpp](https://raw.githubusercontent.com/openjdk/jdk/jdk-22-ga/src/hotspot/share/opto/vectorIntrinsics.cpp).

Một cách hình dung quá trình là:

```text
Mã Java sử dụng Vector API
             |
             v
          Bytecode
             |
             v
Thông dịch / mã biên dịch có profile
             |
             v
JIT tối ưu kernel khi đủ điều kiện
             |
             +--> Ánh xạ phép toán phù hợp sang SIMD
             |
             +--> Giữ hoặc sử dụng triển khai dự phòng
```

Đây là sơ đồ khái niệm. Không phải mọi method đều bắt buộc đi qua từng ô theo cùng một thứ tự; JVM có thể biên dịch lại hoặc tiếp tục thực thi một vòng lặp bằng mã đã tối ưu.

### 4.2. Cold start và trạng thái đã ổn định

Hai câu hỏi hiệu năng khác nhau là:

- **Cold start:** tác vụ hoàn thành trong bao lâu khi JVM vừa khởi động?
- **Steady state:** kernel đạt tốc độ nào sau khi JVM đã thu thập profile và tối ưu?

Một công cụ chạy một lần trên vài kilobyte dữ liệu có thể kết thúc trước khi chi phí tối ưu được bù lại. Một dịch vụ xử lý hàng triệu mảng có thể hưởng lợi rõ hơn từ cùng kernel.

Chạy một lần rồi đo bằng `System.nanoTime()` khó tách các chi phí như nạp lớp, khởi tạo, biên dịch và tính toán. Hãy lựa chọn phép đo theo đặc điểm sử dụng thực tế; warmup dài chỉ trả lời câu hỏi về steady state.

Với HotSpot dùng C1/C2, cấu hình như `-Xint` hoặc `-XX:TieredStopAtLevel=1` làm thay đổi điều kiện đánh giá JIT tối ưu. Có thể dùng cấu hình riêng để khảo sát, nhưng kết quả của nó không đại diện cho dịch vụ chạy cấu hình mặc định.

### 4.3. Cấu trúc mã hỗ trợ JIT

Nên giữ vòng lặp tính toán ngắn, dùng kiểu vector cụ thể và đưa kiểm tra đầu vào ra ngoài vòng lặp. Đặt dữ liệu chính trong mảng primitive; giữ các giá trị vector trung gian trong biến cục bộ.

Ví dụ:

```java
var input = FloatVector.fromArray(SPECIES, values, offset);
var result = input.mul(scale);
result.intoArray(output, offset);
```

Với chuỗi xử lý như vậy, JIT có cơ hội tối ưu các giá trị trung gian trong cùng kernel. Nếu đưa từng vector qua nhiều lớp trừu tượng, lưu vào `List<FloatVector>` hoặc giữ trong các trường đối tượng, cần đánh giá lại chi phí vật thể hóa và khả năng tối ưu. Ghi chú của API lưu ý rằng lưu vector trong field hoặc phần tử mảng có thể phát sinh rủi ro hiệu năng. Nguồn: [Ghi chú hiệu năng của Vector API JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html#performance-notes).

Đây là định hướng để thiết kế kernel dễ đo và dễ quan sát. Nó không bảo đảm JIT sẽ loại bỏ mọi cấp phát trong mọi trường hợp.

## 5. Ba loại đường thực thi dự phòng

### 5.1. Fallback của triển khai API

Khi một phép toán không được biên dịch thành lệnh vector, triển khai mặc định có thể thực hiện phép toán theo scalar. Cơ chế này nằm bên dưới lời gọi API, giúp duy trì khả năng thực thi của chương trình. Tài liệu package xác định có triển khai scalar mặc định cho từng phép toán. Nguồn: [Performance notes của Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html#performance-notes).

Cần hiểu đúng phạm vi:

- Một kernel có nhiều phép toán có thể có những phần được tối ưu khác nhau.
- Không phải một lời gọi API luôn tương ứng đúng một lệnh máy.
- Fallback giữ ngữ nghĩa của phép toán theo hợp đồng API; nó không bảo đảm chi phí bằng một vòng lặp scalar tự viết.
- Lỗi đầu vào như mảng không hợp lệ hoặc truy cập vượt giới hạn vẫn là lỗi cần sửa.

Một phép `mul` được tối ưu tốt không chứng minh một phép shuffle, chuyển kiểu hoặc hàm toán học khác cũng có cùng chất lượng ánh xạ.

### 5.2. Scalar tail của thuật toán

Giả sử một species có tám lane và mảng có 19 phần tử:

```text
Chỉ số:        0 ... 7 | 8 ... 15 | 16 17 18
Phần xử lý:    vector  | vector   | scalar tail
```

Ba phần tử cuối không đủ một vector đầy. Xử lý chúng bằng scalar là quyết định của thuật toán, ngay cả khi máy hỗ trợ SIMD rất tốt. Đây không phải dấu hiệu phần cứng thất bại.

Một lựa chọn khác là dùng mask cho nhóm cuối. Khi đó, mask phải được áp dụng cho những thao tác đọc và ghi cần bảo vệ giới hạn; chỉ mask phép ghi không làm phép đọc vượt mảng trở nên hợp lệ.

Không có quy tắc mọi nền tảng đều ưu tiên masked tail. Với kernel đơn giản, vòng chính không mask và scalar tail là cấu trúc dễ bắt đầu; sau đó so sánh với biến thể dùng mask nếu có nhu cầu. Tài liệu package minh họa cả hai cách và lưu ý chi phí khi dùng mask ở mọi vòng. Nguồn: [Ví dụ vòng lặp và phần tử đuôi trong Vector API JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

### 5.3. Fallback do ứng dụng lựa chọn

Ứng dụng có thể giữ hai implementation và chọn trước khi vào vòng lặp:

- Dùng scalar khi mảng nhỏ hơn ngưỡng đã đo.
- Dùng vector khi workload và môi trường phù hợp.
- Cho phép tắt nhánh vector bằng cấu hình vận hành khi cần điều tra hoặc rollback.

Ngưỡng này là **chính sách hiệu năng của ứng dụng**. Nó không phải phép phát hiện phần cứng và cũng không có giá trị cố định đúng cho mọi CPU.

Ví dụ, `minVectorLength = 256` chỉ có ý nghĩa khi phép đo trên workload đích hỗ trợ lựa chọn đó. Không nên sao chép con số từ một máy khác rồi xem là đặc tính của Vector API.

### 5.4. Thiếu module không phải fallback số học

Phải phân biệt việc không sinh được lệnh SIMD với việc runtime không có module `jdk.incubator.vector`.

Nếu JVM không resolve được module được yêu cầu, chương trình có thể không khởi động được. Nếu một lớp tham chiếu trực tiếp các kiểu vector không nạp được, một nhánh `if` trong lớp đó không tự tạo ra module còn thiếu.

Muốn cung cấp ứng dụng chạy cả trên runtime có và không có module vector, cần thiết kế phần scalar độc lập với các kiểu của Vector API và tách vector implementation thành thành phần tùy chọn. Việc lựa chọn thành phần phải xảy ra trước khi nạp lớp phụ thuộc vector. Đây là vấn đề đóng gói và nạp lớp, cần được thiết kế riêng với chính sách chọn kernel theo kích thước mảng.

## 6. Ví dụ hoàn chỉnh: biến đổi hai mảng float

Xét phép tính độc lập theo phần tử:

```text
out[i] = a[i] * scale + b[i]
```

Ví dụ dưới đây có ba đường gọi:

1. `affineScalar`: implementation tham chiếu bằng vòng lặp thông thường.
2. `affineVector`: vòng chính dùng Vector API, phần đuôi dùng scalar.
3. `affine`: lựa chọn theo cấu hình và ngưỡng do người gọi truyền vào.

Lưu ví dụ học tập với tên `VectorReadinessDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.Objects;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorReadinessDemo {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    private VectorReadinessDemo() {
    }

    private static void validate(float[] a, float[] b, float[] out) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(out, "out");
        if (a.length != b.length || a.length != out.length) {
            throw new IllegalArgumentException(
                    "a, b and out must have equal lengths");
        }
    }

    public static void affineScalar(
            float[] a, float[] b, float[] out, float scale) {
        validate(a, b, out);

        for (int index = 0; index < a.length; index++) {
            out[index] = a[index] * scale + b[index];
        }
    }

    public static void affineVector(
            float[] a, float[] b, float[] out, float scale) {
        validate(a, b, out);

        int index = 0;
        int bound = SPECIES.loopBound(a.length);
        int step = SPECIES.length();

        for (; index < bound; index += step) {
            var left = FloatVector.fromArray(SPECIES, a, index);
            var right = FloatVector.fromArray(SPECIES, b, index);
            var transformed = left.mul(scale).add(right);
            transformed.intoArray(out, index);
        }

        for (; index < a.length; index++) {
            out[index] = a[index] * scale + b[index];
        }
    }

    public static void affine(
            float[] a, float[] b, float[] out, float scale,
            boolean vectorEnabled, int minVectorLength) {
        if (minVectorLength < 0) {
            throw new IllegalArgumentException(
                    "minVectorLength must be non-negative");
        }
        Objects.requireNonNull(a, "a");

        if (vectorEnabled && a.length >= minVectorLength) {
            affineVector(a, b, out, scale);
        } else {
            affineScalar(a, b, out, scale);
        }
    }

    public static void main(String[] args) {
        System.out.println("VM: " + System.getProperty("java.vm.name"));
        System.out.println("JDK: " + Runtime.version());
        System.out.println("Arch: " + System.getProperty("os.arch"));
        System.out.println("Shape: " + SPECIES.vectorShape());
        System.out.println("Bits: " + SPECIES.vectorBitSize());
        System.out.println("Lanes: " + SPECIES.length());

        int count = SPECIES.length() * 3 + 1;
        float[] a = new float[count];
        float[] b = new float[count];
        float[] expected = new float[count];
        float[] actual = new float[count];

        for (int index = 0; index < count; index++) {
            a[index] = (index % 31) - 15.25f;
            b[index] = (index % 19) - 9.5f;
        }

        float scale = 1.25f;
        affineScalar(a, b, expected, scale);
        affineVector(a, b, actual, scale);

        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError("Vector result differs from scalar");
        }

        // Ngưỡng 0 để minh họa chọn nhánh, không phải khuyến nghị tuning.
        affine(a, b, actual, scale, true, 0);
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError("Selected vector result differs");
        }

        affine(a, b, actual, scale, false, 0);
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError("Selected scalar result differs");
        }

        System.out.println("Result check: OK");
        System.out.println("Elements: " + count);
        System.out.println("Scalar tail: " + (count % SPECIES.length()));
    }
}
```

Biên dịch và chạy bằng JDK đang đánh giá:

```powershell
javac --add-modules jdk.incubator.vector -d out VectorReadinessDemo.java
java --add-modules jdk.incubator.vector -cp out demo.VectorReadinessDemo
```

Các lệnh này dành cho người học chạy ví dụ trong thư mục thực hành. Chỉ riêng việc sử dụng Vector API incubator không yêu cầu `--enable-preview`; cờ quan trọng ở đây là `--add-modules`. Nếu chương trình có thêm tính năng preview khác thì phải cấu hình theo tính năng đó.

Với ứng dụng dùng Java Module System, khai báo phụ thuộc tương ứng trong module descriptor:

```java
requires jdk.incubator.vector;
```

### 6.1. Những điểm cần đọc từ ví dụ

`loopBound` chia phạm vi thành phần đầy vector và phần còn dư. Mã không giả định số lane cố định. Với mảng rỗng, hai vòng lặp đều không thực hiện lần nào; với mảng ngắn hơn một vector, toàn bộ công việc nằm ở scalar tail.

Ví dụ cố ý tạo số phần tử bằng `3 * số lane + 1` để có dữ liệu đuôi. Kích thước nhỏ này phù hợp minh họa kết quả, không thích hợp để kết luận về tốc độ.

Biến `vectorEnabled` thể hiện một lựa chọn vận hành. Dù truyền `false`, lớp ví dụ vẫn phụ thuộc vào Vector API do có field `SPECIES`; nó không phải implementation cho runtime thiếu module.

Phép so sánh bằng `Arrays.equals` chỉ xác nhận ví dụ hữu hạn cụ thể. Nó không chứng minh tất cả đầu vào của một thuật toán số đều cho kết quả giống nhau.

### 6.2. Giữ rõ hợp đồng số học

Ví dụ dùng `mul(...).add(...)` để phản ánh phép nhân rồi phép cộng của implementation scalar. Không tùy tiện thay bằng `fma` nếu yêu cầu là giữ cách làm tròn của hai phép toán riêng.

Với thuật toán khác, trước khi so sánh hiệu năng cần xác định:

- Kết quả phải giống từng bit hay chỉ cần sai số trong một giới hạn?
- Có cần xử lý riêng `NaN`, vô cực và số không có dấu không?
- Có phép reduction làm thay đổi cách nhóm phép cộng hay không?

Ví dụ, cộng dồn nhiều phần tử theo nhóm vector có thể có thứ tự kết hợp khác vòng lặp scalar. Khi đề bài cho phép sai số, cần mô tả rõ tiêu chí chấp nhận; khi đề bài yêu cầu chính xác từng bit, tiêu chí đó ràng buộc cách chọn thuật toán.

## 7. Đo hiệu năng bằng JMH

### 7.1. So sánh trên cùng một công việc

Baseline “scalar” trong mã Java chỉ có nghĩa là không viết Vector API trực tiếp. JIT vẫn có thể tự vector hóa một vòng lặp phù hợp. Vì vậy, câu hỏi thực tế là:

> Viết Vector API trực tiếp có cải thiện kết quả so với implementation thông thường dưới cùng JVM và cùng cấu hình triển khai không?

Không nên tắt tối ưu của baseline rồi dùng kết quả đó để khẳng định lợi ích vận hành.

Để phép đo hữu ích, hãy dùng dữ liệu từ state của benchmark, có warmup, có nhiều tiến trình JVM độc lập và bảo đảm đầu ra được quan sát. Các mẫu chính thức của JMH giải thích nguy cơ loại bỏ công việc không dùng kết quả, constant folding và ảnh hưởng profile khi nhiều benchmark chạy chung một JVM. Nguồn: [JMH — DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java), [JMH — ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java), [JMH — Forking](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).

### 7.2. Benchmark minh họa

Trong một project JMH đã cấu hình `jmh-core` và annotation processor `jmh-generator-annprocess`, thêm lớp dưới đây. Project cần có lớp `demo.VectorReadinessDemo` ở phần trước và bật module vector khi biên dịch.

```java
package bench;

import demo.VectorReadinessDemo;
import java.util.Random;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 3, jvmArgsAppend = {
        "--add-modules=jdk.incubator.vector"
})
public class VectorKernelBenchmark {
    @Param({"15", "16", "17", "1024", "1048576"})
    public int size;

    private float[] a;
    private float[] b;
    private float[] out;
    private float scale;

    @Setup(Level.Trial)
    public void prepare() {
        a = new float[size];
        b = new float[size];
        out = new float[size];
        scale = 1.25f;

        Random source = new Random(2026);
        for (int index = 0; index < size; index++) {
            a[index] = source.nextFloat() * 2.0f - 1.0f;
            b[index] = source.nextFloat() * 2.0f - 1.0f;
        }
    }

    @Benchmark
    public void scalar(Blackhole sink) {
        VectorReadinessDemo.affineScalar(a, b, out, scale);
        sink.consume(out);
    }

    @Benchmark
    public void vector(Blackhole sink) {
        VectorReadinessDemo.affineVector(a, b, out, scale);
        sink.consume(out);
    }
}
```

Đầu ra là mảng nằm trong benchmark state và được truyền cho `Blackhole`. Phần cấp phát, sinh dữ liệu nằm ngoài vùng đo. Việc kiểm tra kết quả nên thực hiện riêng trước khi đo, không đặt phép so sánh toàn bộ mảng trong mỗi lần gọi benchmark.

Các giá trị 15, 16 và 17 chỉ là bộ dữ liệu minh họa. Trên máy đích, bổ sung các độ dài `L - 1`, `L`, `L + 1`, `3L + 1` với `L = SPECIES.length()`, cùng kích thước thực tế của ứng dụng.

Nếu project đóng gói benchmark thành `target/benchmarks.jar`, có thể chạy:

```powershell
java --add-modules jdk.incubator.vector -jar target/benchmarks.jar "bench.VectorKernelBenchmark.*"
```

`@Fork` truyền module vào các JVM con dùng để đo. Không chỉ cấu hình JVM khởi chạy bên ngoài rồi bỏ quên các tiến trình fork.

Benchmark trên gọi một kernel xử lý cả mảng. Số `ns/op` là thời gian một lần xử lý mảng, không phải một phần tử. Muốn quy đổi về thời gian mỗi phần tử, chia cho `size` tương ứng.

Không cần thêm vòng lặp gọi kernel hàng nghìn lần bên trong method benchmark chỉ để làm con số nhỏ hơn. JMH đã quản lý quá trình lặp; vòng lặp tự thêm có thể thay đổi cách JIT tối ưu công việc. Nguồn: [JMH — Loops](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java).

### 7.3. Ma trận đo nên bao phủ gì?

| Chiều đánh giá | Các trường hợp cần xem xét |
| --- | --- |
| Kích thước | Mảng nhỏ, sát biên số lane, kích thước thường gặp, mảng lớn |
| Giai đoạn thực thi | JVM mới khởi động và trạng thái đã warmup |
| Môi trường | Các nhóm CPU và JDK thực sự dùng khi triển khai |
| Số luồng | Một luồng và tải đồng thời đại diện |
| Bộ nhớ | Lặp lại cùng dữ liệu và xử lý nhiều vùng dữ liệu khác nhau |
| Implementation | Vòng lặp thông thường, vector, chính sách chọn nhánh nếu có |
| Độ ổn định | Nhiều fork, độ phân tán và sai số của kết quả |

Lặp lại cùng một mảng có thể phản ánh trạng thái dữ liệu nằm trong cache. Workload sản xuất đọc những mảng mới liên tục có thể khác đáng kể; cần thiết kế thêm phép đo phù hợp thay vì suy rộng từ một trường hợp.

Với benchmark throughput, xem xét số lần xử lý mỗi giây. Với latency, so sánh thời gian và phân bố phù hợp. Không dùng hai metric khác nhau để tính một tỷ lệ speedup.

## 8. Thu thập bằng chứng về JIT và mã máy

### 8.1. Log biên dịch là bước quan sát ban đầu

Có thể chạy một phiên chẩn đoán riêng của benchmark và truyền cờ vào các JVM đo:

```powershell
java --add-modules jdk.incubator.vector -jar target/benchmarks.jar "bench.VectorKernelBenchmark.vector" -p size=1048576 -jvmArgsAppend "--add-modules=jdk.incubator.vector -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining"
```

Trong HotSpot:

- `PrintCompilation` hiển thị hoạt động biên dịch method.
- `PrintInlining` cung cấp quyết định inline.
- `UnlockDiagnosticVMOptions` mở các tùy chọn chẩn đoán yêu cầu nó.

Các tùy chọn được mô tả trong [Tài liệu lệnh java của JDK 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html).

Hãy tìm kernel hoặc method của benchmark chứa kernel sau khi inline. Khi dùng HotSpot C1/C2 với tiered compilation, mức 4 là dấu hiệu về biên dịch tối ưu C2; tuy nhiên, thấy method được biên dịch chưa đủ kết luận vòng lặp đã dùng SIMD.

Các log này giúp định hướng điều tra. Chạy phép đo hiệu năng cuối cùng riêng với cấu hình log phù hợp để chi phí ghi log không lẫn vào kết quả.

### 8.2. Mã máy cho biết vòng lặp thực sự làm gì

Muốn quan sát sâu hơn, có thể yêu cầu HotSpot in mã máy của method quan tâm, ví dụ:

```text
-XX:+UnlockDiagnosticVMOptions
-XX:CompileCommand=print,demo.VectorReadinessDemo::affineVector
```

Khi dùng JMH, truyền các cờ ấy cho JVM fork như ở ví dụ trên. Việc in assembly dễ đọc cần disassembler phù hợp với JVM và kiến trúc, thường là thư viện `hsdis`; trên Windows x64, tài liệu nêu tên `hsdis-amd64.dll`. Nguồn: [java — PrintAssembly và CompileCommand](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html).

Nếu kernel bị inline, mã tối ưu có thể nằm trong method gọi nó. Vì vậy, không tìm thấy một bản biên dịch độc lập của `affineVector` chưa có nghĩa kernel không được tối ưu.

Khi đọc mã máy, cần xem vòng lặp đang xử lý mấy phần tử mỗi bước, lệnh nạp/ghi, phép nhân/cộng vector và đường đi của phần đuôi. Một vài lệnh SIMD ở đoạn khởi tạo hoặc sao chép không chứng minh toàn bộ vòng tính toán đã được vector hóa.

Không dùng `javap -c` để chứng minh có AVX hoặc NEON: công cụ đó hiển thị bytecode, còn mã máy của JIT được sinh trong quá trình chạy.

### 8.3. Mức độ mạnh của bằng chứng

| Bằng chứng | Có thể xác nhận | Chưa thể xác nhận |
| --- | --- | --- |
| Chương trình nạp và chạy | Module, lớp và các đầu vào đã dùng hoạt động | Có SIMD hay có lợi ích tốc độ |
| Kết quả khớp baseline | Những ca đã kiểm tra đáp ứng tiêu chí | Toàn bộ miền đầu vào đều đúng |
| Species có nhiều lane | Cấu hình chia dữ liệu của vector | Mọi operator dùng lệnh phần cứng |
| Log JIT có kernel hoặc caller | Đoạn mã đã được biên dịch | Vòng lặp chính có SIMD tối ưu |
| Assembly có vòng lặp SIMD | Lệnh vector hiện diện ở kernel quan tâm | Ứng dụng sẽ nhanh hơn bao nhiêu |
| Benchmark đại diện | Lợi ích và độ ổn định trong điều kiện đo | Mọi máy và mọi tải đều có cùng kết quả |

## 9. Khi đã có SIMD nhưng hiệu năng vẫn thấp

### 9.1. Kernel có thể bị giới hạn bởi bộ nhớ

Với phép `out[i] = a[i] * scale + b[i]`, mỗi phần tử cần đọc hai giá trị `float` và ghi một giá trị `float`. Đó là tối thiểu **12 byte dữ liệu logic** cho một phép nhân và một phép cộng, chưa tính các chi tiết lưu lượng cache và bộ nhớ.

Suy ra từ chính cấu trúc phép tính: nếu kernel đã bị giới hạn bởi tốc độ cung cấp dữ liệu, giảm số lệnh số học không bảo đảm thời gian giảm tương ứng.

Các hướng thử nghiệm hợp lý là xử lý nhiều bước liên tiếp trong cùng lượt duyệt, tránh mảng trung gian không cần thiết và bố trí dữ liệu để truy cập thuận lợi. Chỉ áp dụng khi vẫn giữ hợp đồng thuật toán và phép đo cho thấy có lợi.

### 9.2. Số lane không bằng hệ số tăng tốc

Giả sử một kernel chiếm 20% thời gian của request và phần kernel đó được tăng tốc gấp bốn lần. Nếu các phần còn lại giữ nguyên, tỷ lệ thời gian mới là:

```text
0,80 + 0,20 / 4 = 0,85
```

Hệ số tăng tốc toàn request chỉ khoảng:

```text
1 / 0,85 ≈ 1,18 lần
```

Đây là ví dụ tính toán, không phải số đo của Vector API. Nó cho thấy cần xác định phần việc có thể cải thiện trước khi đầu tư tối ưu kernel.

### 9.3. Bảng định hướng điều tra

| Hiện tượng | Giả thuyết cần xem xét | Bước tiếp theo |
| --- | --- | --- |
| Chậm trong lần chạy đầu | Nạp lớp, khởi tạo hoặc JIT chiếm tỷ trọng lớn | Tách phép đo cold start và steady state |
| Mảng nhỏ chậm hơn baseline | Chi phí cố định và phần đuôi lớn so với công việc | Đo ngưỡng chọn nhánh scalar |
| Chỉ một nhóm CPU chậm | Khác build JDK, feature khả dụng hoặc đặc tính CPU | Ghi lại môi trường và xem mã máy trên nhóm đó |
| Một operator làm giảm tốc rõ | Ánh xạ không thuận lợi hoặc fallback của operator đó | Đo kernel nhỏ hơn chứa phần cần khảo sát |
| Có SIMD nhưng ít tăng tốc | Bộ nhớ hoặc phần khác của ứng dụng chiếm ưu thế | Xem profile toàn luồng xử lý |
| Độ phân tán giữa các fork lớn | Tải hệ thống hoặc điều kiện tài nguyên biến động | Kiểm soát môi trường rồi đo lại |
| Kết quả vector khác scalar | Thay đổi thứ tự số học, FMA hoặc lỗi phạm vi | Xác định hợp đồng kết quả trước khi tuning |
| Không tìm thấy module | Runtime hoặc cấu hình resolve module chưa phù hợp | Kiểm tra đóng gói và lệnh khởi chạy |

Các hàng là giả thuyết để kiểm tra, không phải chẩn đoán chắc chắn từ một triệu chứng duy nhất.

## 10. Quy trình đưa kernel vào ứng dụng

Một quy trình thực hành có thể đi theo thứ tự:

1. **Định nghĩa kết quả đúng.** Mô tả đầu vào, số học, sai số và quyền ghi dữ liệu.
2. **Giữ baseline rõ ràng.** Có implementation thông thường để đối chiếu kết quả và hiệu năng.
3. **Viết kernel thích nghi số lane.** Dùng preferred species, vòng chính rõ ràng và phần đuôi an toàn.
4. **Đánh giá trên môi trường đích.** Ghi build JDK, CPU, cờ JVM và dữ liệu đại diện.
5. **Đo riêng và đo toàn luồng.** Xác nhận lợi ích của kernel có chuyển thành lợi ích cho ứng dụng.
6. **Chọn chính sách vận hành.** Chỉ thêm ngưỡng hoặc công tắc chọn scalar khi có nhu cầu và bằng chứng phù hợp.
7. **Đánh giá lại khi môi trường thay đổi.** Thay JDK, CPU hoặc phân bố kích thước dữ liệu có thể thay đổi lựa chọn tốt nhất.

Ví dụ, một dịch vụ xử lý hàng loạt số liệu có hai nhóm máy triển khai. Nếu kernel chỉ cải thiện rõ trên một nhóm, chính sách có thể cấu hình theo nhóm đã đo, thay vì tự suy đoán từ tên kiến trúc. Khi đổi JDK, cần xem lại cả kết quả đúng lẫn hiệu năng trên các nhóm đó.

## 11. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| Vector API được giới thiệu lần đầu ở Java 22 | Java 22 cung cấp vòng incubator thứ bảy |
| CPU có AVX là mọi phép toán đều nhanh | Cần đánh giá kiểu lane, operator, species và JIT |
| Preferred species là điểm hiệu năng tối ưu cho mọi thuật toán | Đây là lựa chọn nền tảng hữu ích để bắt đầu; workload vẫn cần đo |
| Vector 512 bit luôn tốt hơn vector 256 bit | Lợi ích phụ thuộc môi trường, kernel và nút thắt |
| Số lane bằng hệ số tăng tốc | Chi phí bộ nhớ, phần đuôi và phần việc khác vẫn tồn tại |
| Scalar tail cho thấy máy không hỗ trợ SIMD | Đó là cách xử lý số phần tử không đủ một vector |
| Tắt nhánh vector giúp chạy được khi thiếu module | Cần giải quyết phụ thuộc module và nạp lớp riêng |
| Một lần chạy ra kết quả đúng chứng minh có SIMD | Cần thêm bằng chứng từ JIT hoặc mã máy |
| Baseline viết bằng vòng for chắc chắn chỉ dùng scalar | JIT có thể tự vector hóa vòng lặp đó |
| Incubator đồng nghĩa kiến thức đã lỗi thời | Cần phân biệt trạng thái ổn định của API với giá trị của kỹ thuật |

## 12. Thực hành củng cố

Dùng ví dụ trong bài để thực hiện các hoạt động sau trong môi trường học tập:

1. Ghi lại build JDK, VM, kiến trúc, số bit và số lane của preferred species.
2. Thử mảng rỗng, mảng ngắn hơn một vector, mảng vừa đủ một vector và mảng có phần đuôi; xác định mỗi vòng lặp xử lý bao nhiêu phần tử.
3. So sánh scalar với vector bằng JMH trên kích thước thường gặp của một ứng dụng cụ thể.
4. Thu thập log biên dịch và, khi có công cụ phù hợp, xem vòng lặp trong mã máy.
5. Giải thích kết quả theo ba lớp: tính đúng, lệnh thực thi và hiệu năng.
6. Đề xuất giữ một implementation hay cần chính sách chọn nhánh; dùng số đo của chính môi trường đó để lập luận.

Đầu ra hữu ích của bài thực hành là một bảng môi trường và kết quả đo, kèm kết luận có giới hạn rõ ràng, chẳng hạn: “Với build JDK này, trên nhóm CPU này và mảng kích thước này, kernel vector cải thiện thời gian trung bình ở steady state; mảng nhỏ tiếp tục dùng baseline theo ngưỡng đã đo.”
