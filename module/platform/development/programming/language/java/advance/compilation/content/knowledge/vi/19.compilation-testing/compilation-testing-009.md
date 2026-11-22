# Phân biệt kiểm thử đầu ra bytecode ổn định với chi tiết triển khai dễ đổi

## 1. Vấn đề: bytecode thay đổi có đồng nghĩa với chương trình sai?

Khi biên dịch Java, `javac` biến source thành class file chứa mã lệnh JVM, constant pool, mô tả class/member và những thuộc tính bổ sung. Sau một thay đổi nhỏ của source, phiên bản JDK hoặc tham số compiler, file `.class` có thể khác về byte mà **hành vi quan sát được và API công khai vẫn đúng**. Ngược lại, một class file chỉ khác vài byte ở tên method, descriptor hay access flag có thể phá vỡ consumer.

Vì thế, bài kiểm thử compilation cần trả lời đúng câu hỏi:

> **Đặc điểm nào của đầu ra bytecode là hợp đồng có ý nghĩa với chương trình sử dụng, và đặc điểm nào chỉ là biểu diễn nội bộ có thể thay đổi hợp lệ?**

Ví dụ một method trả về giá sau giảm 10% có thể được viết theo hai cách tương đương với số nguyên không âm:

~~~java
// Biến thể A: thân method minh họa
return cents - cents / 10;
~~~

~~~java
// Biến thể B: thân method minh họa
long tens = cents / 10;
return tens * 9 + cents % 10;
~~~

Hai cách có thể tạo số lượng lệnh JVM, thứ tự lệnh và bảng local variable khác nhau. Với `cents >= 0`, chúng tính cùng kết quả. Một snapshot test yêu cầu `javap -c` giống từng dòng có thể báo lỗi giả, dù hợp đồng thực tế không đổi. Tuy nhiên, đổi kiểu trả về từ `long` sang `int` hoặc bỏ `public` sẽ phá vỡ API mà consumer cần.

Mục tiêu là xác định **invariant** (điều phải giữ) theo nhu cầu sử dụng: kiểu/khả năng truy cập, tính tương thích nhị phân, hành vi, ràng buộc biên dịch, và những thuộc tính class file thực sự được downstream tool hoặc runtime sử dụng. Không nên mặc định rằng “mọi byte đều phải bằng nhau”.

## 2. Class file chứa những nhóm thông tin nào?

Một file `.class` có cấu trúc được JVM định nghĩa. Một số phần ảnh hưởng trực tiếp đến việc link/chạy chương trình; những phần khác phục vụ biên dịch, debug, reflection, instrumentation hoặc tối ưu hóa.

| Thành phần | Ý nghĩa | Có nên so sánh đúng từng byte? |
|---|---|---|
| **Tên class, superclass, interfaces** | Xác định danh tính và quan hệ kiểu | Kiểm tra hợp đồng tên/quan hệ; không cần so toàn file |
| **Access flags** | `public`, `final`, `abstract`, `static`... | Kiểm tra khi có ảnh hưởng đến consumer |
| **Tên + JVM descriptor của method/field** | Ràng buộc lời gọi, kiểu tham số/trả về ở mức JVM | Rất quan trọng cho ABI/binary compatibility |
| **Generic Signature, Exceptions, annotation** | Ngữ nghĩa source/reflection/framework khi được phát hành | Kiểm tra các thuộc tính có vai trò hợp đồng |
| **Code attribute / instructions** | Cách một method được thực thi | Ưu tiên kiểm thử hành vi; chỉ kiểm tra cấu trúc lệnh khi thực sự cần |
| **Constant pool** | Bảng tham chiếu chuỗi, class, method, field, literal... | Chỉ số và cách sắp xếp thường là chi tiết triển khai |
| **LineNumberTable, LocalVariableTable** | Hỗ trợ stack trace/debugger | Thường không phải API chức năng; có thể đổi theo debug flags/source |
| **StackMapTable** | Thông tin phục vụ kiểm chứng type tại bytecode verification | Kiểm tra class có thể load/verify; tránh snapshot raw frame layout |
| **Synthetic/bridge members** | Hỗ trợ generic erasure, lambda hoặc kỹ thuật compiler | Có thể có vai trò ABI; xem tác động đến consumer, không cố định tùy tiện tên/số lượng |
| **Class file major version** | Chỉ định phiên bản class file được JVM hỗ trợ | Kiểm tra khi sản phẩm cam kết chạy trên một Java runtime cụ thể |

Đặc biệt, `descriptor` JVM của method `long afterTenPercent(long)` là `(J)J`: `J` đại diện cho kiểu `long`, dấu ngoặc chứa danh sách tham số và `J` sau ngoặc là kiểu trả về. Nếu descriptor thay đổi, bytecode consumer đã biên dịch có thể gặp `NoSuchMethodError` khi link với library mới.

**Lưu ý quan trọng:** “Không so từng byte” không có nghĩa là mọi phần không phải API đều vô nghĩa. Debug attribute có thể là hợp đồng của trình phân tích coverage; annotation runtime có thể được framework đọc bằng reflection; bridge method có thể cần để duy trì tính tương thích nhị phân. Phải quyết định theo consumer thực tế.

## 3. Các mức hợp đồng ổn định nên kiểm thử

Thay vì một golden snapshot cho toàn bộ `.class`, tách kiểm tra thành những mức có mục đích rõ:

| Mức kiểm thử | Kiểm tra ổn định | Ví dụ phép kiểm |
|---|---|---|
| **Source compatibility** | Mã nguồn consumer có còn biên dịch với API mới không? | Biên dịch fixture consumer cùng library/generated API |
| **Binary compatibility** | Consumer `.class` cũ có còn link/chạy với library mới không? | Chạy client đã biên dịch trước; theo dõi `NoSuchMethodError`/`IllegalAccessError` |
| **API / ABI structure** | Class, member, descriptor, visibility, inheritance, generic signature quan trọng | `javap -public -s` hoặc công cụ ABI phù hợp |
| **Behavior contract** | Input/output, ngoại lệ, side effect, invariant nghiệp vụ | Unit/integration tests |
| **Runtime/JVM compatibility** | Class load, verify và chạy được trên Java tối thiểu hỗ trợ | `--release`, kiểm thử trên JVM đích |
| **Tool-specific contract** | Annotation, metadata hoặc pattern bytecode mà framework/agent dùng | Kiểm tra metadata đã chuẩn hóa hoặc test tích hợp với tool |
| **Binary reproducibility** | Artifact phải giống hệt byte trong cùng điều kiện build | Hash byte/JAR có kiểm soát môi trường và timestamps |

Hai mức cuối là ngoại lệ có lý do: nếu yêu cầu sản phẩm là **reproducible build**, chính sự giống hệt byte trở thành hợp đồng. Nhưng không dùng yêu cầu đó để mặc định chặn mọi thay đổi compiler vô hại trong bài kiểm thử API thông thường.

Source compatibility và binary compatibility cũng khác nhau. Ví dụ generic signature thay đổi có thể khiến source client biên dịch thất bại dù JVM descriptor sau erasure giữ nguyên. Ngược lại, consumer đã biên dịch trước cần member descriptor cũ khi link; việc “compile source mới thành công” chưa đủ bảo đảm old binary vẫn dùng được.

## 4. Ví dụ Java 17: kiểm hợp đồng thay vì snapshot instruction

Tạo hai file độc lập trong một thư mục `src`. Ví dụ thể hiện một class library và một consumer test. Ta kiểm tra **public method signature**, điều kiện đầu vào, kết quả tại các giá trị biên và nội dung ngoại lệ — những thứ consumer thực sự phụ thuộc.

### 4.1. Library cần kiểm tra

File `src/PriceRules.java`:

~~~java
public final class PriceRules {
    private PriceRules() {
    }

    public static long afterTenPercent(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be nonnegative");
        }
        return cents - cents / 10;
    }
}
~~~

Đây là API nhận số tiền không âm dưới dạng số cent nguyên. Nó tính số còn lại sau khi trừ `floor(cents / 10)`, không sử dụng số thực để tránh vấn đề làm tròn. Với số âm, hợp đồng là ném `IllegalArgumentException` cùng thông báo cụ thể.

### 4.2. Consumer kiểm tra cả ABI sử dụng được và hành vi

File `src/ContractCheck.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class ContractCheck {
    private static void equalsLong(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = PriceRules.class.getDeclaredMethod(
                "afterTenPercent", long.class);
        int flags = method.getModifiers();
        if (!Modifier.isPublic(flags)
                || !Modifier.isStatic(flags)
                || method.getReturnType() != long.class) {
            throw new AssertionError("Public static long API changed");
        }
        System.out.println("API: OK");

        equalsLong(0, PriceRules.afterTenPercent(0));
        equalsLong(1, PriceRules.afterTenPercent(1));
        equalsLong(9, PriceRules.afterTenPercent(10));
        equalsLong(18, PriceRules.afterTenPercent(19));
        equalsLong(90, PriceRules.afterTenPercent(100));

        try {
            PriceRules.afterTenPercent(-1);
            throw new AssertionError("Negative amount must fail");
        } catch (IllegalArgumentException expected) {
            if (!"cents must be nonnegative".equals(
                    expected.getMessage())) {
                throw new AssertionError("Exception contract changed");
            }
        }
        System.out.println("Behavior: OK");
    }
}
~~~

Chạy với JDK 17+ (Unix/macOS/Linux):

~~~bash
mkdir -p out
javac --release 17 -d out src/PriceRules.java src/ContractCheck.java
java -cp out ContractCheck
~~~

Trên Windows PowerShell có thể dùng `New-Item -ItemType Directory -Force out` rồi gọi hai lệnh `javac` và `java` như trên. Với source đúng, **stdout chính xác**:

~~~text
API: OK
Behavior: OK
~~~

Ta đã kiểm tra rằng consumer có thể **biên dịch** và **gọi** API, đồng thời xác nhận signature qua reflection. Trong dự án thư viện, nên đặt consumer fixture ở module độc lập để tránh test lén dựa vào member package-private hoặc dependency nội bộ của library.

Lưu ý: reflection ở đây không thay thế bộ công cụ ABI đầy đủ. Nó kiểm được member cụ thể mà fixture quan tâm; không tự kiểm toàn bộ API surface, generic signature, annotation, overloads hay tương thích binary của client đã build trước.

### 4.3. Xem class file bằng `javap`

~~~bash
javap -classpath out -public -s PriceRules
javap -classpath out -c -p PriceRules
javap -classpath out -v PriceRules
~~~

- `-public -s` hiển thị API public và JVM descriptors; với method ví dụ, descriptor là `(J)J`.
- `-c -p` disassemble instructions kể cả member không public, thích hợp **chẩn đoán** hoặc phân tích tối ưu hóa, không mặc nhiên là snapshot regression.
- `-v` cho thêm constant pool, attributes, line numbers nếu có, class-file version, annotation và metadata liên quan. Các số thứ tự constant-pool entry, offsets, line numbers, stack-map-frame layout hoặc tên thành viên sinh bởi compiler có thể đổi khi sửa source, compiler hoặc flags.

Với `--release 17`, class file thông thường được tạo theo **major version 61** (Java 17). Đây là ràng buộc đáng kiểm tra nếu ứng dụng phải chạy trên Java 17. Nhưng **“major version 61” không bảo đảm tương thích runtime hoàn toàn**: class vẫn có thể cần dependency ngoài bị thiếu hoặc gây lỗi khi chạy. Hãy kết hợp compilation với kiểm thử chạy trên runtime đích.

## 5. Minh họa một thay đổi vô hại nhưng bytecode khác

Giữ nguyên tên file, package, class, modifier, tên method, tham số và return type. Chỉ thay thân method `afterTenPercent` bằng:

~~~java
// Thay riêng phần return trong method, sau khi đã kiểm tra cents < 0.
long tens = cents / 10;
return tens * 9 + cents % 10;
~~~

Đây là **đoạn thay thế trong file `PriceRules.java`**, không phải class có thể biên dịch độc lập. Khi `cents >= 0`, phân tích `cents = 10q + r` với `0 <= r < 10` cho thấy:

- Biến thể ban đầu: `cents - cents / 10 = (10q + r) - q = 9q + r`.
- Biến thể thay thế: `(cents / 10) * 9 + cents % 10 = 9q + r`.

Cả hai luôn cùng kết quả trên miền hợp lệ, kể cả `Long.MAX_VALUE` vì `q * 9` không tràn kiểu `long`. Hai biến thể đều giữ kiểm tra âm và cùng thông báo lỗi, nên contract test ở mục 4 phải tiếp tục pass.

Với `javap -c`, bytecode **có thể** khác ở các lệnh chia, nhân, lưu local variable và cộng; không yêu cầu ghi cố định số offset hoặc thứ tự instruction. Hình thức mã do compiler tạo có thể phụ thuộc phiên bản và tùy chọn tối ưu, trong khi API và hành vi vẫn giữ nguyên.

Vì vậy, kiểm thử dạng:

~~~text
EXPECTED: toàn bộ kết quả javap -c của file .class giống hệt snapshot cũ
~~~

thường **quá giòn** đối với mục tiêu đảm bảo API/hành vi. Kiểm thử tốt hơn là “`ContractCheck` biên dịch và chạy thành công”, “method descriptor vẫn là `(J)J`”, và các thuộc tính thật sự được consumer dùng vẫn đúng.

Không suy từ vài test input rằng hai implementation tương đương cho **mọi** input. Trong ví dụ, ta có thể chứng minh toán học trên miền không âm; với thuật toán phức tạp hơn, cần thêm property-based tests, fuzzing và các trường hợp biên.

## 6. Những chi tiết triển khai dễ thay đổi và bẫy snapshot

### 6.1. Constant pool index và thứ tự bảng

Bytecode dùng index để trỏ vào constant pool. Khi compiler thêm một literal hoặc method reference, cách sắp xếp entry có thể thay đổi; các index như `#12`, `#34` trong `javap -v` không phải danh tính API. Nếu muốn kiểm rằng class thật sự gọi một API nhất định, hãy so **tham chiếu ký hiệu** đã resolve (owner/name/descriptor) hoặc dùng bộ đọc class file, thay vì đóng đinh index.

### 6.2. Instruction offsets, labels và local variable slots

Offset như `0: aload_0`, `5: invokevirtual` hay số slot local là hệ quả của cách compiler triển khai method. Thêm một biến tạm, thay cách biểu diễn vòng lặp hoặc thay tối ưu hóa có thể thay offset mà không thay kết quả. Đừng snapshot offset trừ khi bài toán yêu cầu kiểm đúng layout bytecode (ví dụ kiểm chứng bytecode transformer có ràng buộc đặc biệt).

### 6.3. Debug attributes và compiler flags

`LineNumberTable`, `LocalVariableTable` và `SourceFile` có thể phụ thuộc vào `-g` và nội dung source. Chúng hữu ích cho debugger, stack trace và tooling nhưng không luôn là hợp đồng công khai của thư viện. Nếu sản phẩm yêu cầu source map/coverage đáng tin, kiểm thuộc tính phục vụ **nhu cầu đó**, chẳng hạn khả năng quy chiếu stack trace, thay vì so toàn bộ raw table.

`-parameters` có thể làm compiler phát sinh `MethodParameters` để reflection đọc tên tham số. Với framework dựa vào tên parameter, đây lại **có thể là hợp đồng thực tế**. Không gom tất cả metadata vào nhóm “được phép đổi”.

### 6.4. Synthetic methods, bridge methods, lambda và invokedynamic

Compiler có thể sinh bridge method để bảo đảm dispatch khi dùng generic, hoặc dùng `invokedynamic` và bootstrap metadata cho lambda/string concatenation. Không khóa mọi tên synthetic method hoặc thứ tự bootstrap entry chỉ vì snapshot nhìn thấy chúng. Tuy nhiên, với thư viện cần binary compatibility, bridge method hoặc metadata bootstrap thiếu/sai có thể làm client bị lỗi. Cần có test tương thích với consumer thực tế và, khi thích hợp, công cụ so ABI/class structure theo ký hiệu.

### 6.5. JAR timestamp, entry order và hash

Ngay cả khi nội dung các `.class` không đổi, hai file `.jar` có thể khác byte do thứ tự ZIP entries hoặc timestamp. Nếu mục tiêu chỉ là kiểm API/hành vi, hash JAR không phải oracle phù hợp. Nếu mục tiêu là **reproducible artifact**, phải kiểm hash và chuẩn hóa các nguồn bất định: compiler/toolchain, dependencies, encoding, timezone/path tác động, thứ tự entries và timestamps khi đóng gói. Với Gradle, có thể cấu hình cơ chế reproducible archives cho task đóng gói phù hợp và kiểm thử tính tái lập riêng.

## 7. Khi nào cần kiểm cấu trúc bytecode?

Một số công cụ tiêu thụ **chính bytecode** chứ không chỉ API/hành vi của chương trình:

| Nhu cầu | Kiểm tra có giá trị | Kiểm tra nên tránh |
|---|---|---|
| Code instrumentation / AOP | Sau transform, class verify/load/chạy đúng; advice được áp dụng tại join point mong muốn | Toàn bộ `javap -v` phải giữ thứ tự dòng cũ |
| Security policy giới hạn API/lệnh | Không còn invocation tới owner/name/descriptor bị cấm; không dùng opcode bị cấm theo policy | Tìm chuỗi text tình cờ trong constant pool |
| ABI thư viện dùng chung | Exported type/member/descriptor/visibility, generic signature và bridge method cần thiết | So raw constant pool index |
| Java agent / bytecode enhancer | Frame hợp lệ, method/field cụ thể tồn tại, hành vi trước/sau đúng | Đòi số lượng frame, label, instruction offset bất biến |
| Annotation-driven framework | Annotation retention/target và runtime-visible metadata mà framework đọc | Cố định mọi attribute mà framework không dùng |
| Reproducible binary delivery | Hash SHA-256 giống nhau giữa các build có môi trường được khóa | Dùng hash để thay thế unit/API test |

Khi phải đọc bytecode có cấu trúc, có thể dùng thư viện class-file parser (ví dụ ASM với phiên bản hỗ trợ class-file đang xử lý), rồi **chuẩn hóa** biểu diễn: chọn class/method/field quan trọng, so symbolic owner/name/descriptor, chỉ giữ instruction pattern thật sự thuộc policy. Không tự parse văn bản `javap` bằng regex giòn nếu quyết định bảo mật/tương thích phụ thuộc độ chính xác. Một số kiểm tra nên kết hợp cả static structure lẫn thực thi trên JVM.

Đối với lỗi verifier, chạy class qua `java` trên runtime đích để phát hiện `VerifyError` trong đường thực thi cần thiết; chỉ disassemble được không đồng nghĩa JVM đã chấp nhận class.

## 8. Lựa chọn phép thử theo loại thay đổi

**Thay implementation nhưng giữ API:** chạy compiler fixture, behavioral tests và kiểm tra descriptor/member công khai. Có thể giữ `javap -c` làm tài liệu chẩn đoán; không dùng output của nó làm điều kiện pass/fail mặc định.

**Nâng JDK hoặc compiler options:** khóa `--release` theo JVM tối thiểu hỗ trợ, chạy fixture và tests trên runtime mục tiêu. Kiểm tra class-file major version nếu là contract. Chấp nhận bytecode khác khi API và yêu cầu runtime được giữ; điều tra bất kỳ khác biệt hành vi nào.

**Đổi API của library:** kiểm source compatibility và binary compatibility với consumer cũ. Method có thể cùng tên/kiểu source nhìn gần giống nhưng đổi return descriptor hoặc static/instance sẽ khiến consumer đã build thất bại. Kết hợp công cụ ABI diff với chạy client đã biên dịch trước, không tự động tin vào unit test compile lại toàn bộ.

**Thay code generator / annotation processor:** dùng consumer fixture thật để biên dịch generated sources; xác minh package, public signature, generic/annotation và các entry points. Nếu generated method đổi tên do refactor implementation nhưng consumer không phụ thuộc trực tiếp, đừng khóa tên nội bộ. Nếu generated source được xuất bản làm API, nó trở thành hợp đồng public cần giữ.

**Thay bytecode transformer:** xác minh transform trên nhiều cấu trúc method, stack frames, control flow, bridge/synthetic members khi liên quan; load và thực thi class. Bên cạnh semantic tests, kiểm pattern/opcode nếu đó là yêu cầu rõ của transformer.

**Yêu cầu bit-for-bit reproducibility:** chạy hai build sạch cùng input/toolchain đã khóa tại những workspace/máy có môi trường được kiểm soát và so SHA-256. Khi khác, tìm nguồn bất định trong `.class`, metadata, JAR ordering và timestamps. Đây là bài toán bổ sung, có tiêu chí riêng.

## 9. Những lỗi diễn giải phổ biến

**“Hash `.class` khác, nên compiler regression.”** Không đủ bằng chứng. Hash khác chỉ chứng minh byte khác. Hãy tìm API/hành vi/JVM compatibility khác trước hoặc xác nhận yêu cầu reproducibility.

**“`javap -c` có thêm vài lệnh, nghĩa là chương trình chậm hơn.”** Số lượng lệnh bytecode không thể suy trực tiếp thành chi phí runtime vì JIT optimization, inlining, profiling và escape analysis. Dùng benchmark có phương pháp phù hợp khi đánh giá hiệu năng.

**“Public method vẫn có tên cũ nên binary compatible.”** Chưa đủ. JVM linkage phụ thuộc descriptor, nơi khai báo, visibility và static/instance semantics; generic/source compatibility và bridge methods còn tạo những trường hợp tinh tế.

**“Metadata debug không phải code nên có thể bỏ hết.”** Không đúng với hệ thống phụ thuộc parameter names, runtime annotations, coverage, serialization metadata hoặc instrumentation. Phân loại metadata theo consumer.

**“Source compile lại được nên client cũ chắc chắn chạy.”** Source compatibility của source hiện tại không tự bảo đảm binary compatibility của class đã biên dịch trước. Cần test old binary với library mới.

**“Dùng golden bytecode snapshot càng chặt càng tốt.”** Snapshot chặt nhưng sai mức trừu tượng gây test lỗi giả, làm khóa compiler/toolchain ngẫu nhiên và ngăn refactor lành mạnh. Chỉ cố định byte-level output khi nó thực sự là đặc tả bàn giao.

## 10. Checklist thiết kế bộ kiểm thử bytecode ổn định

- [ ] Ghi rõ consumer và ràng buộc thật: source, binary, behavioral, runtime, tool-specific hay reproducible binary.
- [ ] Dùng compiler fixture hoặc client thực tế để kiểm public API, tránh chỉ kiểm file `.class` tồn tại.
- [ ] Kiểm class/member/descriptor/visibility và generic/annotation khi chúng thuộc hợp đồng.
- [ ] Kiểm hành vi, lỗi, ngoại lệ và biên dữ liệu bằng executable tests; không dùng số lượng instruction thay thế.
- [ ] Xác minh `--release`/class-file version/JVM thực tế khi cam kết hỗ trợ một Java version.
- [ ] Với binary compatibility, kiểm client đã biên dịch trước với library mới.
- [ ] Với bytecode tooling, inspect symbolic structure và chạy load/verify/instrumentation tests phù hợp.
- [ ] Không snapshot raw constant-pool indices, local variable slots, instruction offsets và debug line numbers nếu không có lý do kỹ thuật cụ thể.
- [ ] Tách kiểm thử reproducibility/hash artifact ra khỏi test correctness thông thường.
- [ ] Duy trì một ví dụ thay implementation mà tests vẫn xanh, và một ví dụ cố ý phá API khiến tests đỏ.

**Kết luận cần nhớ:** bytecode là định dạng thực thi, nhưng **không phải mọi byte trong đó đều là hợp đồng**. Hãy kiểm những thuộc tính mà consumer/JVM/công cụ phụ thuộc và kiểm hành vi bằng chương trình thực; cho phép những chi tiết triển khai hợp lệ thay đổi. Chỉ yêu cầu output giống byte-for-byte khi tính tái lập nhị phân là mục tiêu được phát biểu rõ.
