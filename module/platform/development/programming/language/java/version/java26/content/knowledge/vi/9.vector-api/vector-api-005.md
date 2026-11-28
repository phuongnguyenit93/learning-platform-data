# Chọn species thích hợp trên phần cứng đích

Vector API biểu diễn dữ liệu số thành các vector gồm nhiều lane và cho phép thực hiện một phép toán trên nhiều phần tử cùng lúc theo mô hình SIMD (Single Instruction, Multiple Data). Trong API này, VectorSpecies xác định kiểu phần tử và hình dạng vector. Chọn species phù hợp quyết định mỗi vector chứa bao nhiêu lane, cách các vector kết hợp với nhau và khả năng ánh xạ phép toán xuống phần cứng.

Với code cần chạy trên nhiều máy, lựa chọn khởi đầu nên là species được nền tảng ưu tiên, chẳng hạn FloatVector.SPECIES_PREFERRED hoặc IntVector.SPECIES_PREFERRED. Chỉ chọn shape cố định như 256 bit hoặc 512 bit khi phần cứng triển khai được kiểm soát và kết quả benchmark chứng minh lựa chọn đó có lợi. Một shape rộng hơn không tự động nhanh hơn: nếu CPU không hỗ trợ shape đó, JVM có thể dùng implementation scalar thay cho lệnh SIMD tương ứng.

Vector API trong JDK 26 vẫn là incubator module theo JEP 529 (Eleventh Incubator). API có thể thay đổi hoặc bị loại bỏ trong JDK tương lai; nó chưa phải API Java SE ổn định. Bài thực hành này dùng API hiện hành của JDK 26, phân biệt cách chọn species với cách đo hiệu năng trên máy đích và nêu rõ điều kiện khi đưa module incubator vào ứng dụng.

## 1. Vector, lane, shape và species

Một vector là một dãy cố định các lane. Mỗi lane chứa một giá trị thuộc cùng kiểu nguyên thủy, chẳng hạn byte, short, int, long, float hoặc double. Một phép toán lane-wise áp dụng phép toán scalar tương ứng lên từng cặp lane.

Bốn khái niệm cần phân biệt:

- **Element type**: kiểu dữ liệu của mỗi lane, ví dụ float hoặc int.
- **Shape**: tổng số bit của vector, ví dụ 128, 256 hoặc 512 bit.
- **Lane count**: số phần tử trong vector, bằng vectorBitSize chia cho elementSize.
- **Species**: tổ hợp element type và shape, xác định kiểu vector cụ thể mà phép toán sẽ sử dụng.

Ví dụ, vector float có shape 256 bit chứa 8 lane vì mỗi float có 32 bit. Vector double cùng shape chứa 4 lane vì mỗi double có 64 bit.

| Species | Element size | Vector size | Lane count |
|---|---:|---:|---:|
| Float, 128 bit | 32 bit | 128 bit | 4 |
| Float, 256 bit | 32 bit | 256 bit | 8 |
| Float, 512 bit | 32 bit | 512 bit | 16 |
| Double, 256 bit | 64 bit | 256 bit | 4 |
| Int, 512 bit | 32 bit | 512 bit | 16 |
| Byte, 128 bit | 8 bit | 128 bit | 16 |

Các con số trên chỉ mô tả sức chứa logic của vector. Chúng không khẳng định CPU đang chạy có thanh ghi hoặc lệnh SIMD tương ứng.

Một species được biểu diễn bằng VectorSpecies<E>. Mỗi vector, mask và shuffle liên quan đều gắn với species cụ thể. Các phép toán lane-wise thông thường yêu cầu các vector đầu vào có cùng shape và số lane. Khi ghép dữ liệu từ nhiều vector, hãy bảo đảm chúng dùng cùng species.

## 2. Vì sao chọn species ảnh hưởng đến hiệu năng?

Vector API cung cấp một mô hình độc lập tương đối với phần cứng. Code biểu diễn phép toán trên vector, còn runtime và JIT compiler quyết định cách hạ các phép toán đó thành lệnh SIMD phù hợp.

Giả sử một vòng lặp xử lý 1.000.000 phần tử float. Nếu species có 8 lane, một vòng vector xử lý 8 phần tử. Nếu species có 16 lane, mỗi vòng xử lý 16 phần tử. Nhưng số lane lớn hơn chỉ giúp tăng throughput khi CPU hỗ trợ shape, phép toán có thể được vector hóa hiệu quả và dữ liệu không bị giới hạn bởi yếu tố khác.

Một shape không được hỗ trợ vẫn có thể chạy đúng nhờ implementation mặc định của Vector API, nhưng không nhất thiết được biên dịch thành lệnh SIMD. Tài liệu JDK 26 nêu rõ ví dụ IntVector 512 bit trên nền tảng chỉ hỗ trợ vector 256 bit có thể dùng scalar implementation. Vì vậy, chọn shape lớn nhất theo tên gọi không phải chiến lược tối ưu chung.

Hiệu năng thực tế còn phụ thuộc vào:

- Kiến trúc CPU và tập lệnh SIMD mà CPU hỗ trợ.
- Phiên bản JDK và chất lượng tối ưu hóa của JIT compiler.
- Kiểu phần tử và loại phép toán.
- Dữ liệu nằm trong cache hay phải đọc từ bộ nhớ chính.
- Kích thước mảng, số phần tử dư ở cuối vòng lặp và độ phức tạp của truy cập bộ nhớ.
- Chi phí chuyển đổi dữ liệu, mask, shuffle và các thao tác không lane-wise.
- Mức độ nóng của code sau khi JIT biên dịch.

Species giúp chọn hình dạng dữ liệu cho phép tính. Nó không thay thế việc đo benchmark trên phần cứng đích.

## 3. Các lựa chọn species trong JDK 26

Các lớp vector chuyên biệt cung cấp species tương ứng với kiểu phần tử:

~~~java
FloatVector.SPECIES_PREFERRED
FloatVector.SPECIES_MAX
FloatVector.SPECIES_128
FloatVector.SPECIES_256
FloatVector.SPECIES_512

IntVector.SPECIES_PREFERRED
IntVector.SPECIES_MAX
IntVector.SPECIES_128
IntVector.SPECIES_256
IntVector.SPECIES_512
~~~

Không phải mọi shape đều được hỗ trợ hiệu quả trên mọi nền tảng. Ý nghĩa của các lựa chọn chính:

| Lựa chọn | Ý nghĩa | Khi nên dùng |
|---|---|---|
| SPECIES_PREFERRED | Shape được nền tảng ưu tiên cho kiểu lane; các preferred species dùng chung một shape | Mặc định cho thuật toán cần chạy trên nhiều phần cứng |
| SPECIES_MAX | Shape lớn nhất mà nền tảng hỗ trợ cho kiểu lane cụ thể | Khi thuật toán chỉ dùng một kiểu lane và đã đo trên máy mục tiêu |
| SPECIES_128 / 256 / 512 | Shape có độ rộng cố định | Khi phần cứng triển khai được kiểm soát, cần so sánh hoặc tối ưu riêng một môi trường |

Có thể lấy species bằng các phương thức tĩnh của VectorSpecies:

~~~java
VectorSpecies<Float> preferred =
    VectorSpecies.ofPreferred(float.class);

VectorSpecies<Float> largestForFloat =
    VectorSpecies.ofLargestShape(float.class);

VectorSpecies<Float> fixed256 =
    VectorSpecies.of(float.class, VectorShape.S_256_BIT);
~~~

SPECIES_PREFERRED thường là điểm bắt đầu tốt nhất vì nó chọn shape chung có thể hỗ trợ tất cả kiểu lane. Điều này đặc biệt hữu ích nếu thuật toán cần reinterpret hoặc chuyển đổi giữa các kiểu phần tử khác nhau. SPECIES_MAX chọn shape lớn nhất cho một kiểu lane cụ thể; shape đó có thể lớn hơn preferred nhưng không nhất thiết phù hợp cho mọi kiểu lane khác.

## 4. Kiểm tra species mà JVM chọn trên máy đích

Không nên suy luận shape từ tên CPU hoặc giả định rằng mọi máy x86 đều có AVX-512. Hãy truy vấn trực tiếp species tại runtime:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class SpeciesInfo {
    private static final VectorSpecies<Float> FLOAT_SPECIES =
        FloatVector.SPECIES_PREFERRED;

    private static final VectorSpecies<Integer> INT_SPECIES =
        IntVector.SPECIES_PREFERRED;

    private static void print(String name, VectorSpecies<?> species) {
        System.out.printf(
            "%s: shape=%s, bits=%d, laneBits=%d, lanes=%d%n",
            name,
            species.vectorShape(),
            species.vectorBitSize(),
            species.elementSize(),
            species.length()
        );
    }

    public static void main(String[] args) {
        print("float preferred", FLOAT_SPECIES);
        print("int preferred", INT_SPECIES);
        print("float max", FloatVector.SPECIES_MAX);
        print("float 256", FloatVector.SPECIES_256);
    }
}
~~~

Biên dịch và chạy bằng JDK có module Vector API:

~~~sh
javac --add-modules jdk.incubator.vector SpeciesInfo.java
java --add-modules jdk.incubator.vector SpeciesInfo
~~~

Kết quả sẽ cho biết shape, tổng số bit, số bit mỗi lane và lane count mà species đại diện. Giá trị cụ thể phụ thuộc JDK, kiến trúc và nền tảng chạy.

Có thể kiểm tra module hiện diện trong runtime:

~~~sh
java --list-modules
java --describe-module jdk.incubator.vector
~~~

Trên Windows PowerShell, lọc danh sách module:

~~~powershell
java --list-modules | Select-String 'jdk.incubator.vector'
~~~

Thông tin species cho biết lựa chọn của API tại runtime. Nó không chứng minh rằng mọi phép toán trong chương trình đã được JIT biên dịch thành lệnh SIMD. Muốn xác nhận điều đó, cần benchmark và kiểm tra mã máy bằng công cụ phù hợp với hệ điều hành, JDK và CPU.

## 5. Dùng SPECIES_PREFERRED cho code đa nền tảng

Ví dụ dưới đây tính kết quả y[i] = x[i] * factor + bias[i]. Code dùng preferred species, xử lý các khối vector đầy đủ rồi xử lý phần dư bằng vòng lặp scalar.

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

import java.util.Objects;

public class ScaleAndBias {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    public static void apply(
            float[] x,
            float[] bias,
            float factor,
            float[] output) {

        Objects.requireNonNull(x);
        Objects.requireNonNull(bias);
        Objects.requireNonNull(output);

        if (x.length != bias.length || x.length != output.length) {
            throw new IllegalArgumentException(
                "Arrays must have the same length"
            );
        }

        FloatVector factorVector =
            FloatVector.broadcast(SPECIES, factor);

        int i = 0;
        int upperBound = SPECIES.loopBound(x.length);

        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector vx = FloatVector.fromArray(SPECIES, x, i);
            FloatVector vbias = FloatVector.fromArray(SPECIES, bias, i);

            FloatVector result = vx.mul(factorVector).add(vbias);
            result.intoArray(output, i);
        }

        // Xử lý các phần tử không đủ một vector.
        for (; i < x.length; i++) {
            output[i] = x[i] * factor + bias[i];
        }
    }

    public static void main(String[] args) {
        float[] x = {1, 2, 3, 4, 5, 6, 7, 8, 9};
        float[] bias = {10, 10, 10, 10, 10, 10, 10, 10, 10};
        float[] output = new float[x.length];

        apply(x, bias, 2.0f, output);

        System.out.println(
            "Preferred lanes: " + SPECIES.length()
        );
        System.out.println(java.util.Arrays.toString(output));
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --add-modules jdk.incubator.vector -d out ScaleAndBias.java
java --add-modules jdk.incubator.vector -cp out ScaleAndBias
~~~

Trong vòng lặp vector:

- SPECIES.length() cho biết số phần tử được xử lý mỗi vòng.
- SPECIES.loopBound(x.length) trả về giới hạn lớn nhất không vượt quá độ dài mảng và là bội số của lane count.
- fromArray đọc một vector đầy đủ từ mảng.
- mul và add thực hiện phép toán theo từng lane.
- intoArray ghi kết quả về đúng vị trí tương ứng.

Phần tử còn lại được xử lý bằng scalar loop. Không tự tính giới hạn bằng biểu thức bit như length & ~(species.length() - 1), vì không nên giả định mọi lane count đều là lũy thừa của hai. loopBound thể hiện đúng ý nghĩa và không phụ thuộc giả định đó.

## 6. Dùng mask cho phần dư

Một cách khác là xử lý cả khối cuối bằng mask. indexInRange tạo mask chỉ bật những lane có chỉ số nằm trong giới hạn mảng.

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public class MaskedScale {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    static void multiply(
            float[] left,
            float[] right,
            float[] output) {

        if (left.length != right.length ||
                left.length != output.length) {
            throw new IllegalArgumentException("Length mismatch");
        }

        for (int i = 0; i < left.length; i += SPECIES.length()) {
            VectorMask<Float> mask =
                SPECIES.indexInRange(i, left.length);

            FloatVector a =
                FloatVector.fromArray(SPECIES, left, i, mask);
            FloatVector b =
                FloatVector.fromArray(SPECIES, right, i, mask);

            a.mul(b).intoArray(output, i, mask);
        }
    }
}
~~~

Mask bảo vệ thao tác load và store ở phần cuối, tránh truy cập vượt giới hạn mảng. Đây là cách viết gọn khi muốn dùng cùng một vòng lặp. Tuy nhiên, tài liệu JDK 26 lưu ý rằng dùng mask ở mọi vòng lặp có thể không tối ưu bằng cách chỉ dùng vector cho phần đầy đủ rồi xử lý tail scalar, nhất là khi mảng lớn.

Hãy đo cả hai cách trên workload thật. Masked loop có thể thuận tiện hoặc nhanh hơn với một số kiểu xử lý; không có một quy tắc hiệu năng đúng cho mọi CPU và mọi kích thước dữ liệu.

## 7. Khi nào chọn shape cố định?

Giả sử một ứng dụng chỉ triển khai trên một nhóm máy có cùng CPU và JDK. Có thể benchmark một vài species cố định:

~~~java
VectorSpecies<Float> s128 = FloatVector.SPECIES_128;
VectorSpecies<Float> s256 = FloatVector.SPECIES_256;
VectorSpecies<Float> s512 = FloatVector.SPECIES_512;
VectorSpecies<Float> preferred = FloatVector.SPECIES_PREFERRED;
VectorSpecies<Float> maximum = FloatVector.SPECIES_MAX;
~~~

Không chọn 512 bit chỉ vì nó có nhiều lane hơn. Nếu CPU chỉ hỗ trợ vector 256 bit, thao tác với species 512 bit có thể dùng scalar implementation. Nếu CPU hỗ trợ 512 bit nhưng workload bị giới hạn bởi băng thông bộ nhớ, species rộng hơn cũng có thể không cải thiện throughput.

Một quy trình chọn shape cố định nên gồm:

1. Xác định chính xác CPU và JDK trong môi trường triển khai.
2. Ghi nhận preferred species và maximum species tại runtime.
3. Chọn các fixed species có ý nghĩa để benchmark.
4. So sánh với preferred species và scalar implementation.
5. Kiểm tra kết quả trên tất cả cấu hình phần cứng mà ứng dụng hỗ trợ.
6. Chỉ giữ shape cố định nếu lợi ích đủ lớn và môi trường triển khai thực sự được kiểm soát.

Nếu ứng dụng chạy trên nhiều kiến trúc, nên để species được chọn tại runtime thay vì hard-code shape theo máy phát triển. Có thể đóng gói phần tính toán trong một lớp nội bộ để sau này đổi API hoặc cách chọn species mà không ảnh hưởng toàn bộ ứng dụng.

## 8. Khi thuật toán dùng nhiều kiểu lane

SPECIES_PREFERRED có lợi thế là các preferred species của các kiểu lane khác nhau có chung underlying shape. Ví dụ, preferred species cho float, int và long có cùng vectorBitSize trên cùng runtime; số lane sẽ thay đổi theo kích thước từng lane.

Ngược lại, SPECIES_MAX chọn shape lớn nhất cho một kiểu lane cụ thể. Nếu thuật toán cần reinterpret giữa float và int, dùng các species preferred thường thuận tiện hơn vì shape được giữ chung. Nếu dùng species max độc lập cho từng kiểu, shape có thể khác nhau và việc reinterpret hoặc kết hợp vector cần xử lý rõ ràng.

Ví dụ truy vấn và so sánh:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class CompareSpecies {
    public static void main(String[] args) {
        VectorSpecies<Float> floats =
            FloatVector.SPECIES_PREFERRED;
        VectorSpecies<Integer> ints =
            IntVector.SPECIES_PREFERRED;

        System.out.println(floats.vectorShape());
        System.out.println(ints.vectorShape());

        System.out.println(
            "Same bit size: " +
            (floats.vectorBitSize() == ints.vectorBitSize())
        );
    }
}
~~~

Không nên giả định hai vector có cùng lane count chỉ vì cùng preferred shape. Float có 32 bit mỗi lane, int cũng 32 bit; nhưng long và double có 64 bit mỗi lane nên lane count sẽ ít hơn khi vectorBitSize giữ nguyên.

## 9. Kiểm tra giới hạn phần cứng và fallback

Vector API được thiết kế để chạy đúng cả khi nền tảng không có phần cứng SIMD chuyên dụng. Trong trường hợp runtime không thể biên dịch một phép toán sang vector instruction, implementation scalar mặc định có thể được sử dụng. Điều này bảo vệ tính đúng đắn và tính di động của code, nhưng không đảm bảo hiệu năng tăng.

Tài liệu performance notes của JDK 26 nêu rõ:

- Shape được chọn nên được hỗ trợ bởi nền tảng.
- Ví dụ vector 512 bit trên máy chỉ hỗ trợ vector 256 bit có thể dùng scalar implementation.
- Dùng preferred species giúp viết thuật toán có shape thích nghi theo nền tảng.
- Species nên được giữ trong biến local, tham số hoặc static final; không nên lưu tùy tiện trong các field thông thường hoặc phần tử mảng vì có thể gây bất lợi hiệu năng.
- Vector, VectorMask, VectorShuffle và VectorSpecies là các kiểu value-based; tránh phụ thuộc vào object identity hoặc so sánh bằng ==.

Không suy luận hỗ trợ SIMD chỉ từ việc chương trình biên dịch và chạy thành công. Phải kiểm tra JDK, CPU, species thực tế và hiệu năng trên đúng máy đích.

## 10. Đo hiệu năng để quyết định species

Một benchmark đáng tin cậy cần so sánh ít nhất ba trường hợp:

- Scalar loop với cùng thuật toán.
- Vector API dùng SPECIES_PREFERRED.
- Các species cố định cần đánh giá trên phần cứng đích.

Dùng JMH cho microbenchmark Java thay vì tự đo thời gian bằng System.currentTimeMillis hoặc nanoTime trong một vòng lặp đơn giản. JMH giúp quản lý warmup, fork, iteration và tránh một số lỗi phổ biến của benchmark JVM.

Khi đo:

1. Dùng cùng dữ liệu đầu vào, cùng thuật toán và cùng điều kiện kiểm tra kết quả.
2. Chạy warmup đủ để JIT biên dịch code trước khi lấy số đo.
3. Thử nhiều kích thước dữ liệu: nhỏ hơn một vector, vừa đúng nhiều vector và có phần dư.
4. Đo cả dữ liệu nằm trong cache và dữ liệu lớn hơn cache.
5. Giữ output có thể quan sát để tránh dead-code elimination.
6. Chạy benchmark trên đúng CPU, hệ điều hành và JDK dự kiến triển khai.
7. Lặp lại trên các máy thuộc nhóm phần cứng được hỗ trợ.
8. Kiểm tra độ lệch kết quả số thực nếu thuật toán thay đổi thứ tự tính toán hoặc dùng FMA.
9. Nếu cần xác nhận lệnh máy, dùng profiler phù hợp với JDK và hệ điều hành; đừng suy ra SIMD chỉ từ thời gian chạy.

Các workload xử lý mảng lớn thường có thể bị giới hạn bởi băng thông bộ nhớ. Trong trường hợp đó, tăng số lane không nhất thiết làm throughput tăng tương ứng. Với workload nhỏ, chi phí gọi hàm, tạo mask, truy cập bộ nhớ hoặc khởi động có thể lớn hơn lợi ích SIMD.

## 11. Cấu hình module và trạng thái incubator

Vector API nằm trong module jdk.incubator.vector. Khi dùng trên classpath, truyền module lúc biên dịch và chạy:

~~~sh
javac --add-modules jdk.incubator.vector -d out SpeciesInfo.java
java --add-modules jdk.incubator.vector -cp out SpeciesInfo
~~~

Nếu dùng module-info.java, khai báo dependency:

~~~java
module com.example.vector {
    requires jdk.incubator.vector;
}
~~~

Vector API không phải preview language feature, vì vậy không cần --enable-preview chỉ để dùng module này. Cần phân biệt:

| Trạng thái | Cách bật |
|---|---|
| Incubator module như jdk.incubator.vector | --add-modules jdk.incubator.vector hoặc requires trong module-info.java |
| Preview language/API feature | --enable-preview và phiên bản release tương ứng |
| API Java SE chính thức | Dùng trực tiếp, không cần cờ incubator hoặc preview |

JEP 529 đưa Vector API vào JDK 26 ở lần incubator thứ mười một. Tài liệu module của JDK 26 vẫn đánh dấu đây là Incubating Feature và cảnh báo module có thể bị loại bỏ trong một bản phát hành tương lai. Do đó:

- Không đưa kiểu Vector API vào public API của thư viện có nhiều người dùng nếu chưa chấp nhận rủi ro tương thích.
- Không giả định chữ ký API sẽ ổn định giữa các JDK.
- Cô lập phần code phụ thuộc module trong một package hoặc adapter nội bộ.
- Kiểm tra lại Javadoc và release notes của đúng JDK khi nâng cấp.
- Nếu cần hợp đồng Java SE ổn định, cân nhắc scalar implementation hoặc thư viện đã có chính sách tương thích phù hợp.

Không dùng ví dụ cũ của incubator trước đây mà không kiểm tra JDK mục tiêu. API có thể đã đổi tên, đổi overload hoặc thêm loại dữ liệu kể từ các vòng incubator trước.

## 12. Lỗi thường gặp khi chọn species

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chọn SPECIES_512 nhưng không nhanh hơn | CPU không hỗ trợ shape hoặc workload bị giới hạn bởi bộ nhớ | So sánh preferred, maximum và scalar trên máy đích |
| Code chạy đúng nhưng không có SIMD | Runtime dùng scalar implementation cho shape/phép toán không được hỗ trợ | Kiểm tra performance notes và mã máy nếu cần |
| Hai vector không kết hợp được | Khác species, shape hoặc lane count | Dùng cùng species cho các đầu vào lane-wise |
| Truy cập vượt cuối mảng | Vòng lặp vector không xử lý tail | Dùng loopBound + scalar tail hoặc mask indexInRange |
| Tính tail sai | Tự giả định lane count là lũy thừa của hai | Dùng SPECIES.loopBound thay vì bit trick |
| Kết quả số thực hơi khác scalar | Thứ tự phép toán hoặc FMA khác | Xác định tolerance và yêu cầu độ chính xác |
| Benchmark lúc nhanh lúc chậm | Đo trước warmup, dữ liệu khác nhau hoặc nhiễu hệ thống | Dùng JMH, warmup và nhiều lần fork |
| Code phụ thuộc một CPU cụ thể | Hard-code shape hoặc giả định tập lệnh | Dùng preferred species hoặc runtime dispatch có kiểm thử |
| Không tìm thấy package jdk.incubator.vector | Chưa thêm module khi compile/run hoặc JDK không có module | Kiểm tra JDK và truyền --add-modules |
| Nghĩ Vector API là preview | Nhầm incubator module với preview feature | Phân biệt module incubator và cờ preview |

## 13. Checklist chọn species cho môi trường đích

- [ ] Đã xác định kiểu lane đúng với dữ liệu và phép toán.
- [ ] Đã dùng SPECIES_PREFERRED làm baseline cho code đa nền tảng.
- [ ] Đã kiểm tra vectorBitSize, elementSize và length tại runtime.
- [ ] Đã phân biệt SPECIES_PREFERRED với SPECIES_MAX.
- [ ] Chỉ dùng shape cố định khi phần cứng triển khai được kiểm soát.
- [ ] Các vector tham gia phép toán lane-wise dùng cùng species.
- [ ] Đã xử lý tail bằng loopBound hoặc mask indexInRange.
- [ ] Không giả định lane count là lũy thừa của hai.
- [ ] Đã benchmark scalar, preferred và fixed species bằng JMH.
- [ ] Đã kiểm tra trên CPU, JDK và hệ điều hành đích.
- [ ] Đã xác minh hiệu năng không chỉ dựa trên việc code chạy thành công.
- [ ] Đã cô lập dependency incubator và có kế hoạch nâng cấp API.
- [ ] Đã kiểm tra tài liệu JDK 26 thay vì dựa vào ví dụ từ các vòng incubator cũ.

## Tài liệu tham khảo

- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): trạng thái incubator của Vector API trong JDK 26.
- [Java SE 26 — jdk.incubator.vector package](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): ví dụ dùng preferred species, xử lý tail và ghi chú hiệu năng.
- [Java SE 26 — VectorSpecies API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html): element type, shape, lane count, loopBound, indexInRange, ofPreferred và ofLargestShape.
- [Java SE 26 — VectorShape API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html): shape, preferredShape và largestShapeFor.
- [Java SE 26 — Vector API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html): mô hình lane-wise, yêu cầu cùng species và cách biểu diễn SIMD.
- [Java SE 26 — FloatVector API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html): species và thao tác vector trên float.

