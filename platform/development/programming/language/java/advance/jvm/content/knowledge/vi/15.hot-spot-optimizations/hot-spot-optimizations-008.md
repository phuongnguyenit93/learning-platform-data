# Intrinsic và phụ thuộc vào kiến trúc CPU, JDK, cách triển khai

## 1. Intrinsic giải quyết vấn đề gì?

**Intrinsic** trong HotSpot là cơ chế JVM/JIT nhận ra một method hoặc thao tác thư viện Java đã biết và **có thể** thay đường biên dịch/thực thi thông thường bằng **compiler IR chuyên biệt, mã máy viết riêng hoặc runtime stub**. Tối ưu này tận dụng kiến thức mà compiler có về thư viện, CPU và runtime để làm công việc tương đương nhanh hơn.

Ví dụ, những operations có khả năng được HotSpot triển khai bằng intrinsics trên phần cứng phù hợp gồm:

- Đếm bit: `Integer.bitCount`, đếm leading/trailing zero bits.
- `Math.sqrt`, `Math.fma` và một số phép toán exact.
- `System.arraycopy`, so sánh arrays/strings theo đường chuyên biệt.
- Checksums `CRC32`, `CRC32C`; AES/SHA và các thuật toán xử lý crypto phù hợp.
- Một số operations nội bộ của BigInteger, Base64, runtime và atomic operations.

**Từ quan trọng nhất là “có thể”.** Có method ứng viên không có nghĩa mọi lần gọi sẽ được intrinsify. HotSpot phải xét phiên bản JDK, nền tảng CPU, cấu hình flags, compiler tier, method/call-site, JIT compilation state, input shape và các guards.

**Ba tầng khác nhau:**

1. **Java API contract:** kết quả, exception và các hành vi phải giữ.
2. **HotSpot implementation:** method nào có intrinsic ID, compiler/stub nào hỗ trợ, flags nào bật.
3. **CPU/hệ điều hành:** ISA extensions và khả năng VM dùng được những tính năng ấy.

~~~text
Java code:
  x = Integer.bitCount(mask);
              |
              v
      Library method call
              |
              v
  HotSpot nhận diện candidate?
       /               \
      No               Yes
      |                 |
      v                 v
 Normal path     Intrinsic path khả dụng?
                         /       \
                       Yes        No
                        |          |
                        v          v
                   Target IR/   Fallback
                   stub/code   library code
                        |          |
                        +-----+----+
                              |
                              v
                     Same Java result
~~~

**Intrinsics không phải thành phần bắt buộc của JVMS.** Bytecode Java portable theo JVM semantics; còn native compiled code mang tính phụ thuộc CPU/JVM.

## 2. Phân biệt intrinsic với method inlining

**Inlining** thường mở body của callee vào compiler IR của caller. **Intrinsification** thay/special-case operation bằng code hoặc IR do HotSpot biết riêng; nó có thể không giống body Java của callee.

~~~java
static int addOne(int x) {
    return x + 1;
}

static int compute(int n) {
    return addOne(n) * 2;
}
~~~

Hai methods trên là minh họa, không phải file Java chạy độc lập.

- Với **inlining**, optimizer có thể đưa body `addOne` vào `compute` và nhìn một biểu thức `(n + 1) * 2`.
- Với **intrinsic**, ví dụ `Integer.bitCount`, optimizer có thể dùng specialized bit-count node hoặc instruction sequence mà không cần triển khai từng bước giống Java library bytecode.

| Tiêu chí | Inlining | Intrinsic |
| --- | --- | --- |
| Nguyên lý | Mở callee IR ở call site | Thay/special-case bằng VM-known representation |
| Dựa vào method body? | Thường có | Không nhất thiết |
| Cần CPU instruction đặc biệt? | Không | Không bắt buộc; có thể dùng nhiều instructions/stub |
| Có thể đi kèm? | Có | Có |
| Bảo đảm dùng cho mọi call? | Không | Không |
| Cần đúng Java semantics? | Có | Có |

**Không thể suy** từ việc `javap -c` vẫn hiển thị `invokestatic` rằng JIT không dùng intrinsic: `javap` xem **class-file bytecode**, không phải optimized native code.

## 3. `@IntrinsicCandidate` là internal annotation, không phải lệnh ép JIT

OpenJDK có `jdk.internal.vm.annotation.IntrinsicCandidate`. Tài liệu trong source annotation cho biết:

- Một method/constructor được đánh dấu **có thể được HotSpot intrinsify**.
- Việc đánh dấu **không bảo đảm** intrinsic thực sự dùng trên mọi platform/cấu hình.
- Chỉ dành cho **JDK library maintainers**, không phải API ổn định cho application.
- Khi thư viện/HotSpot thay đổi, người bảo trì phải đảm bảo checks và semantics tương thích.
- Với `CheckIntrinsics`, HotSpot có thể kiểm tra sự nhất quán giữa các method được annotate và danh sách VM intrinsics khi loading class.

Không viết:

~~~java
// KHÔNG dùng trong application thông thường:
// @jdk.internal.vm.annotation.IntrinsicCandidate
// public static int fastWork(int x) { ... }
~~~

Annotation nội bộ **không tự tạo HotSpot intrinsic implementation** cho method tự viết. Thậm chí import package nội bộ `jdk.internal.*` vi phạm mục tiêu portable Java application và có thể bị module system hạn chế.

### Danh sách intrinsic ID ở đâu?

Trong HotSpot source, `src/hotspot/share/classfile/vmIntrinsics.hpp` mô tả các intrinsic IDs, method signatures và điều kiện liên quan. Nó phân biệt những intrinsic **được compiler thay bằng code/IR** và những **bytecode intrinsic** được compiler xử lý đặc biệt theo cách khác.

Danh mục này thay đổi qua JDK releases. Code ở nhánh OpenJDK `master` có thể khác JDK 17 hoặc JDK 25 trên máy; kiểm tra đúng **tag/branch tương ứng** khi cần nghiên cứu kỹ.

## 4. Giữ đúng ngữ nghĩa Java mới là điều bắt buộc

Mọi optimization phải giữ **kết quả và observable behavior được Java API bảo vệ**.

| Đối tượng | Nghĩa cần được giữ |
| --- | --- |
| `Integer.bitCount` | Đếm đúng số bit 1 theo biểu diễn nhị phân |
| `Math.fma` | **Fused** multiply-add rounding, không được thay tùy ý bằng hai phép được làm tròn riêng |
| `Math.addExact` | Ném `ArithmeticException` khi integer overflow |
| `System.arraycopy` | Bounds/null/type checks, overlap handling, partial copy khi type mismatch |
| Crypto digest | Algorithm/provider semantics và bytes output đúng |
| Atomic/volatile | Java Memory Model, atomicity và ordering phù hợp |
| Arrays/reference ops | Object identity, type safety, GC write barriers khi cần |

OpenJDK `IntrinsicCandidate` lưu ý đường intrinsic có thể không tự thực hiện các checks giống hệt Java method body **nếu checks đã nằm ở đường caller/guard tương đương**. Nhưng toàn bộ execution path phải đáp ứng contract; không thể “tối ưu” bằng cách cho phép truy cập ngoài bounds hay trả checksum sai.

**Compiler intrinsic không có nghĩa chỉ một CPU instruction.** Nó có thể là IR node mở rộng thành nhiều machine instructions, call tới stub native đặc biệt, hoặc nhánh code specialized với fallback.

## 5. Phụ thuộc CPU và ISA extensions

Một machine instruction chỉ tồn tại nếu CPU thực hỗ trợ feature tương ứng và VM được phép sử dụng nó. Ví dụ về các họ lệnh:

| Khả năng hardware | Ví dụ nhóm ISA | Java operation có thể được hỗ trợ |
| --- | --- | --- |
| Population count | x86 POPCNT, các phép đếm bit ARM | `Integer.bitCount` |
| Leading/trailing zero count | x86 LZCNT/TZCNT/BSR hoặc AArch64 CLZ và idioms khác | `numberOfLeadingZeros`, `numberOfTrailingZeros` |
| SIMD/vector | SSE/AVX trên x86, NEON/SVE trên ARM thích hợp | Arrays/strings/vectorized routines |
| AES acceleration | AES-NI trên một số x86, ARM crypto extensions | AES implementations |
| CRC | CRC instructions trên CPU hỗ trợ | CRC32C hoặc đường checksum tương ứng |
| SHA acceleration | SHA extensions của các CPU phù hợp | SHA provider code paths |
| Fused multiply-add | x86 FMA hoặc ARM64 FMA | `Math.fma` trên HotSpot phù hợp |

**Đặc biệt dễ nhầm:** CPU instruction x86 có tên `CRC32` thuộc nhóm CRC-32C (Castagnoli) phù hợp, **không có nghĩa mặc nhiên là IEEE CRC32 của `java.util.zip.CRC32`**. JVM phải sử dụng đúng thuật toán; hai cái có polynomial khác nhau.

Cùng một kiến trúc x86-64 không có nghĩa mọi chip có AVX-512, AES-NI, FMA hay POPCNT; extensions phụ thuộc CPU generation và feature bits. Trong virtual machines/hypervisor, một số features còn có thể bị mask.

### Fallback khi không có lệnh CPU

~~~text
Java API contract (không đổi)
              |
              v
HotSpot tìm hardware/VM-supported fast path
        /                \
       Có                Không
       |                   |
  specialized          ordinary optimized code /
  instruction/stub     library/software fallback
       |                   |
       +---------+---------+
                 |
                 v
          Observable result đúng
~~~

Thiếu acceleration **không có nghĩa Java API phải lỗi**. Java code gọi `Integer.bitCount` hoặc `CRC32.update` vẫn có implementation hợp lệ trên JVM/platform phù hợp, dù tốc độ có thể khác.

## 6. Intrinsic có thể thay đổi theo JDK và compiler

Cùng một Java binary, các môi trường có thể khác nhau ở nhiều chiều:

- **JDK release:** danh sách intrinsics, library methods, signatures và compiler improvements thay đổi.
- **JVM vendor:** HotSpot, OpenJ9 và những runtime khác có implementations/flags khác.
- **Compiler:** HotSpot C1, C2, JVMCI/Graal có khả năng intrinsify và policies khác nhau.
- **CPU/OS:** hardware features, platform backends, instruction selection và calling conventions khác.
- **JVM flags:** những nhóm UseXXXIntrinsics có thể bật/tắt tùy cấu hình.
- **Runtime state:** method hot chưa, JIT compile chưa, call-site shape và input type có phù hợp không.
- **Provider:** một `MessageDigest` hay `Cipher` có thể dùng provider khác với code path khác.

Một method **được JVM biết là intrinsic candidate** vẫn có thể được chạy bằng bytecode/library path nếu chưa compile hoặc đường intrinsic không khả dụng ở call site cụ thể.

**Sự khác biệt codegen không đồng nghĩa khác kết quả Java.** Trên HotSpot JDK 17 và JDK 25, native instruction sequence có thể khác, nhưng application vẫn phải quan sát semantics của Java API.

## 7. Ví dụ bit intrinsics: kết quả không đổi

Các biểu thức:

~~~java
int bits = Integer.bitCount(0xF0F0F0F0);
int leading = Integer.numberOfLeadingZeros(1);
int trailing = Long.numberOfTrailingZeros(1L << 40);
~~~

Là statements minh họa, không phải chương trình độc lập. Theo Java semantics:

- `0xF0F0F0F0` có 4 byte F0, mỗi byte có 4 bit 1, nên `bitCount` trả **16**.
- 1 trong 32 bit có **31 leading zeros**.
- `1L << 40` có bit đầu tiên ở vị trí 40 tính từ LSB, nên trailing zeros là **40**.

Trên CPU có POPCNT/LZCNT/TZCNT/CLZ phù hợp, JIT có thể sinh optimized instructions. Không suy ngược từ kết quả 16/31/40 ra CPU opcode đã thực thi: constant folding hoặc fallback cũng có thể cho cùng kết quả.

## 8. `Math.fma` và `Math.addExact` minh họa ràng buộc correctness

### Fused multiply-add

~~~java
double v = Math.fma(2.0, 3.0, 4.0); // 10.0
~~~

`Math.fma` có fused semantics: kết quả tương đương multiplication và addition với một rounding step theo API contract, không phải tùy ý thay bằng phép nhân rồi cộng với hai rounding steps. Với một số dữ liệu dấu phẩy động, `a * b + c` có thể cho kết quả khác `Math.fma(a,b,c)`.

Oracle JDK 25 `java` manual mô tả `-XX:+UseFMA` cho hardware-based FMA intrinsics trên những hệ thống có lệnh phù hợp (ví dụ các CPU Intel/ARM64 hỗ trợ). Trên CPU thiếu FMA extension, VM phải dùng implementation tương thích nếu API vẫn được hỗ trợ.

### Exact arithmetic

~~~java
Math.addExact(Integer.MAX_VALUE, 1);
~~~

Theo API, đoạn đó **ném `ArithmeticException`**. Oracle JDK 25 mô tả nhóm `-XX:+UseMathExactIntrinsics`. Intrinsic có thể tăng tốc phép toán kèm overflow check nhưng **không** được đổi thành `int` wraparound và âm thầm trả về `Integer.MIN_VALUE`.

## 9. `System.arraycopy`: không thể là memcpy mù quáng

`System.arraycopy` là ví dụ kinh điển về thao tác có thể được JVM tối ưu rất sâu nhưng phải giữ những điều kiện:

- Kiểm tra source/destination là arrays và không null.
- Kiểm tra vị trí, chiều dài, bounds và array component types.
- Nếu source/destination overlap, bảo toàn kết quả tương đương phép copy qua vùng tạm.
- Với reference arrays, kiểm tra assignability; nếu phần tử thứ k sai kiểu, phần prefix hợp lệ phía trước vẫn có thể được copy rồi `ArrayStoreException` được ném.
- Với arrays chứa references, cần các GC barriers/card marking phù hợp để object graph vẫn đúng.

Ví dụ:

~~~java
int[] a = {1, 2, 3, 4, 5};
System.arraycopy(a, 0, a, 1, 4);
// a = [1, 1, 2, 3, 4]
~~~

Nếu dùng routine copy forward thiếu xử lý overlap, kết quả có thể sai. Một arraycopy intrinsic phải chọn đúng direction/code path/guard, hoặc fallback.

**Không phải mọi `System.arraycopy` sẽ đi qua đúng cùng một stub.** Array type, length, alignment, overlap, CPU, GC và compiler decisions đều có thể ảnh hưởng.

## 10. CRC, SHA, AES và các flags HotSpot

Oracle JDK 25 `java` manual ghi các nhóm intrinsics:

| Nhóm thao tác | Flag có trong JDK 25 manual | Phụ thuộc |
| --- | --- | --- |
| CRC32 | `-XX:+UseCRC32Intrinsics` | CPU/backend support |
| CRC32C | `-XX:+UseCRC32CIntrinsics` | CPU/backend support |
| AES | `-XX:+UseAES`, `-XX:+UseAESIntrinsics` | Hardware AES extension |
| AES/CTR | `-XX:+UseAESCTRIntrinsics` | Algorithm/mode/hardware |
| GHASH | `-XX:+UseGHASHIntrinsics` | Crypto platform |
| SHA | `-XX:+UseSHA`, `-XX:+UseSHA256Intrinsics` và các variants | CPU/provider |
| Base64 | `-XX:+UseBASE64Intrinsics` | JVM/platform support |
| Adler32 | `-XX:+UseAdler32Intrinsics` | Build/platform |
| Math exact | `-XX:+UseMathExactIntrinsics` | Compiler path |
| BigInteger | `UseMultiplyToLenIntrinsic` và nhóm khác | Architecture/compiler |

**JDK 25 yêu cầu `-XX:+UnlockDiagnosticVMOptions` cho các flags kiểm soát intrinsics được nêu trong manual.** Ví dụ:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32Intrinsics ChecksumIntrinsicDemo
~~~

Cờ chỉ có hiệu lực khi VM hỗ trợ; không tự tạo lệnh hardware nếu CPU thiếu. Dùng bản JDK khác nên kiểm tra docs/`java -version`.

### SHA provider không phải chi tiết phụ

`MessageDigest.getInstance("SHA-256")` lấy algorithm từ Java Security provider. Oracle JDK 25 có giới hạn về đường SHA hardware intrinsics trên provider `sun.security.provider.Sun` phù hợp. Vì vậy **không khẳng định mọi provider bên thứ ba đều được tăng tốc** bằng cùng HotSpot intrinsic.

**Intrinsic không làm thuật toán mật mã trở nên an toàn hơn về thiết kế.** Algorithm, mode, key, nonce, provider và side-channel considerations vẫn cần xử lý đúng.

## 11. Java 17+ runnable: bit, math, arraycopy, mismatch

Tạo file **`IntrinsicBasicsDemo.java`**:

~~~java
import java.util.Arrays;

public class IntrinsicBasicsDemo {
    public static void main(String[] args) {
        System.out.println("bitcount=" + Integer.bitCount(0xF0F0F0F0));
        System.out.println("leading=" + Integer.numberOfLeadingZeros(1));
        System.out.println("trailing=" + Long.numberOfTrailingZeros(1L << 40));

        System.out.println("sqrt=" + Math.sqrt(81.0));
        System.out.println("fma=" + Math.fma(2.0, 3.0, 4.0));

        int[] source = {10, 20, 30, 40};
        int[] dest = new int[3];
        System.arraycopy(source, 1, dest, 0, 3);
        System.out.println("copied=" + Arrays.toString(dest));

        byte[] left = {1, 2, 3};
        byte[] right = {1, 2, 4};
        System.out.println("mismatch=" + Arrays.mismatch(left, right));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -g IntrinsicBasicsDemo.java
java IntrinsicBasicsDemo
~~~

**Stdout chính xác khi chương trình hoàn tất bình thường:**

~~~text
bitcount=16
leading=31
trailing=40
sqrt=9.0
fma=10.0
copied=[20, 30, 40]
mismatch=2
~~~

Bài thực hành thể hiện **Java API semantics**, **không** chứng minh JVM sinh opcode POPCNT, FMA hay SIMD. JIT có thể constant-fold vì inputs cố định. Chạy `javap -c -p IntrinsicBasicsDemo` chỉ xem bytecode, không xem compiled native instructions.

## 12. Java 17+ runnable: CRC32, CRC32C và SHA-256

Tạo file **`ChecksumIntrinsicDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.zip.CRC32;
import java.util.zip.CRC32C;

public class ChecksumIntrinsicDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] data = "123456789".getBytes(StandardCharsets.US_ASCII);

        CRC32 crc32 = new CRC32();
        crc32.update(data, 0, data.length);
        System.out.printf("crc32=%08x%n", crc32.getValue());

        CRC32C crc32c = new CRC32C();
        crc32c.update(data, 0, data.length);
        System.out.printf("crc32c=%08x%n", crc32c.getValue());

        byte[] sha = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.US_ASCII));
        System.out.println("sha256=" + HexFormat.of().formatHex(sha));
    }
}
~~~

Chạy:

~~~bash
javac -g ChecksumIntrinsicDemo.java
java ChecksumIntrinsicDemo
~~~

**Stdout chuẩn trên một JDK có SHA-256 provider khả dụng:**

~~~text
crc32=cbf43926
crc32c=e3069283
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Hai CRC có **polynomials khác nhau** nên kết quả chuẩn khác nhau; SHA-256 của chuỗi ASCII `abc` là test vector phổ biến. Nếu runtime cấu hình không có SHA-256 provider, method có thể ném `NoSuchAlgorithmException`, không phải intrinsic gây sai digest.

Thử với flags khi HotSpot hỗ trợ:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32Intrinsics ChecksumIntrinsicDemo
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32CIntrinsics ChecksumIntrinsicDemo
~~~

**Kết quả API vẫn đúng** khi chương trình chạy thành công. Thay cờ chỉ thay những code paths được VM phép sử dụng, không đổi thuật toán hay test vectors.

## 13. Java 17+ runnable: exceptions vẫn được bảo toàn

Tạo file **`ArrayCopySemanticsDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayCopySemanticsDemo {
    public static void main(String[] args) {
        int[] overlap = {1, 2, 3, 4, 5};
        System.arraycopy(overlap, 0, overlap, 1, 4);
        System.out.println("overlap=" + Arrays.toString(overlap));

        Object[] mixed = {"ok", Integer.valueOf(17)};
        String[] target = new String[2];
        try {
            System.arraycopy(mixed, 0, target, 0, 2);
            System.out.println("unexpected-success");
        } catch (ArrayStoreException e) {
            System.out.println("caught=ArrayStoreException");
        }
        System.out.println("partial=" + Arrays.toString(target));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("unexpected-success");
        } catch (ArithmeticException e) {
            System.out.println("caught=ArithmeticException");
        }
    }
}
~~~

~~~bash
javac -g ArrayCopySemanticsDemo.java
java ArrayCopySemanticsDemo
~~~

**Stdout chính xác:**

~~~text
overlap=[1, 1, 2, 3, 4]
caught=ArrayStoreException
partial=[ok, null]
caught=ArithmeticException
~~~

Trong arraycopy từ `Object[]` sang `String[]`, `"ok"` được copy trước, rồi `Integer` bị từ chối, nên target chứa `[ok, null]`. `addExact` phải ném exception khi tràn. **Dù HotSpot dùng intrinsics hay fallback, kết quả này vẫn phải hợp lệ**.

## 14. Flags bật khác chứng minh intrinsic thực sự chạy

Có bốn câu hỏi độc lập:

1. **JVM biết intrinsic ID không?** — source `vmIntrinsics.hpp` theo đúng JDK version.
2. **CPU/flags cho phép không?** — platform detection/VM initialization.
3. **Compiler/runtime có chọn intrinsic tại call site này không?** — profiling, tier, hotness, inputs, fallback.
4. **Native code thực tế là gì?** — compiler logs, disassembly hoặc profiling thích hợp.

Một flag `UseCRC32Intrinsics=true` chỉ cho biết **cấu hình cho phép**, chưa chứng minh method `CRC32.update` ở chỗ bạn nghiên cứu thực sự đi qua hardware instruction.

Cùng một method có thể:

- Chạy interpreted vì chưa đủ hot.
- Được C1 compile nhưng không dùng đường C2 tối ưu đặc biệt.
- Được C2 compile và intrinsify.
- Bị constant-fold vì input cố định.
- Gọi runtime stub chuyên biệt.
- Dùng fallback khi CPU thiếu instructions hoặc flags tắt.

**Không suy “intrinsics chỉ hoạt động ở C2” cho mọi VM operation.** HotSpot có compiler intrinsics lẫn runtime/library special-case paths, và mỗi tier/build có capabilities khác nhau.

## 15. Hướng dẫn quan sát HotSpot

Bắt đầu từ phiên bản/flags thật:

~~~bash
java -version
java -Xlog:help
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintFlagsFinal -version
~~~

Có thể xem compilation/inlining:

~~~bash
java -XX:+PrintCompilation IntrinsicBasicsDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation IntrinsicBasicsDemo
~~~

**Diagnostics có thể thêm dòng log**, nên stdout toàn process khi bật chúng không còn chỉ gồm các dòng output chương trình.

| Công cụ | Cho biết | Không chứng minh |
| --- | --- | --- |
| `java -version` | Vendor, JDK release, VM | Call site nào dùng intrinsic |
| `PrintFlagsFinal` | VM flag values | Compiled method đã dùng acceleration |
| `PrintCompilation` | Method compile events | CPU instruction cụ thể |
| `PrintInlining` | Inlining decisions | Mọi intrinsic path đã chạy |
| `LogCompilation` | Compiler log khi hỗ trợ | Thời gian chạy chuẩn khi logging bật |
| `PrintAssembly` + hsdis | Machine code theo công cụ hỗ trợ | Toàn bộ program/call sites nếu không capture đủ |
| JFR và profiler | Runtime behavior/alloc/CPU | Intrinsic codegen nếu không có instruction evidence |
| JMH | Microbenchmark hiệu năng | Bảo đảm intrinsic được sử dụng |

Oracle JDK 25 `java` manual mô tả `PrintAssembly` có thể cần external `hsdis` library. Không bắt buộc tải binary không rõ nguồn. Trên JVM khác HotSpot, những flags `-XX` có thể không tồn tại hoặc khác semantics.

### Fine-grained intrinsic controls

Trong OpenJDK HotSpot, `vmIntrinsics.hpp` có các control mechanisms như `ControlIntrinsic` / `DisableIntrinsic` bên cạnh nhóm `UseXXXIntrinsics`. Danh sách IDs và cú pháp phụ thuộc bản VM, nên **không đoán tên intrinsic ID từ Java method name** để thử trên production. Dùng flags nhóm chính thức đã tài liệu hóa sẽ dễ kiểm chứng hơn.

## 16. Đo hiệu năng intrinsic đúng cách

Một chương trình chỉ in `Integer.bitCount(0xFF)` **không phải benchmark POPCNT**, vì compiler có thể tính trước giá trị ngay lúc compile. Để nghiên cứu performance:

1. Sử dụng **JMH** với warmup/measurement iterations/forks phù hợp.
2. Tạo inputs thay đổi ở runtime, phản ánh kích thước và phân bố thực.
3. Dùng Blackhole hoặc consumption để tránh dead-code elimination.
4. So sánh **cùng JDK/CPU/workload** và chỉ thay một VM flag được hỗ trợ.
5. Tránh `println` hay verbose logs bên trong vùng đo.
6. Ghi rõ compiler tier, CPU ISA, provider và JVM flags.
7. Kiểm tra compiled machine code nếu mục tiêu là xác nhận opcode/ISA.
8. Báo kết quả biến thiên, throughput/latency, không chỉ một con số một lần chạy.

**Intrinsic không luôn nhanh hơn:** với input rất nhỏ, startup hoặc overhead guards/stubs chiếm ưu thế, đường code khác có thể tương đương hoặc tốt hơn. Thay đổi CPU/JDK/provider cùng lúc khiến so sánh không xác định được nguyên nhân.

### Production troubleshooting

Nếu throughput CRC/SHA khác nhau giữa nodes:

- Ghi `java -version` và flags `UseCRC32Intrinsics`/`UseSHA*Intrinsics`.
- Kiểm tra CPU feature masks, virtualization/hypervisor.
- Kiểm tra Java Security provider thực được chọn.
- So sánh compiled code/profile trên workload đã warmup.
- Xem CPU frequency, system load, GC và I/O để tránh gán mọi chênh lệch cho intrinsic.

Không chỉnh disable/enable intrinsic trên production trước khi kiểm chứng ở môi trường test.

## 17. Các ngộ nhận thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Intrinsic là bytecode mới.” | Thường là VM/compiler special case cho method/operation. |
| “`@IntrinsicCandidate` buộc HotSpot sử dụng.” | Chỉ đánh dấu candidate, không bảo đảm. |
| “Annotation trên method tự viết tạo intrinsic.” | Không; cần implementation trong VM. |
| “Một intrinsic luôn là một CPU instruction.” | Có thể là IR, nhiều instructions hoặc stub. |
| “Intrinsic = inlining.” | Không, có thể phối hợp nhưng cơ chế khác. |
| “Intrinsic lúc nào cũng nhanh hơn.” | Cần benchmark trên workload/CPU/JDK cụ thể. |
| “Tất cả CPU x86-64 có AES-NI/AVX-512.” | ISA extensions phụ thuộc hardware và feature masks. |
| “CPU instruction CRC32 là Java CRC32.” | x86 CRC32 tương ứng CRC32C polynomial trong ngữ cảnh thích hợp. |
| “JDK 17 và 25 buộc sinh cùng machine code.” | Compiler/library/backend thay đổi theo release. |
| “C1 và C2 hỗ trợ intrinsics giống hệt.” | Có thể khác. |
| “`javap -c` hiện calls chứng minh không intrinsic.” | `javap` chỉ xem bytecode. |
| “Flag UseXXX=true chứng minh opcode đã chạy.” | Chỉ cho biết điều kiện có thể cho phép. |
| “Tắt CRC32 intrinsic làm checksum khác.” | Java API contract không đổi. |
| “`Math.fma` luôn tương đương `a*b+c` về rounding.” | Fused semantics có thể khác. |
| “Arraycopy intrinsic được bỏ type checks.” | Exception/partial copy semantics phải được bảo toàn. |
| “CPU thiếu AES làm Java Cipher luôn lỗi.” | Provider có thể dùng software implementation đúng. |
| “SHA providers nào cũng dùng cùng HotSpot intrinsic.” | Provider/code path ảnh hưởng. |
| “Dùng JNI native method tự động thành intrinsic.” | JNI và compiler intrinsics khác nhau. |
| “JMH tự chứng minh CPU instruction.” | JMH đo performance; cần codegen evidence. |
| “Flags -XX thuộc Java standard.” | Vendor-specific, có thể khác theo build/version. |
| “Crypto nhanh bằng intrinsic nghĩa mode/key design an toàn.” | Security requirements độc lập với tốc độ. |

## 18. Tự kiểm tra có đáp án

**1.** Intrinsic là gì?  
**Đáp án:** HotSpot có thể special-case một method/operation qua compiler IR, machine code hoặc runtime stub để tối ưu.

**2.** `@IntrinsicCandidate` có bảo đảm được intrinsify?  
**Đáp án:** Không. Runtime CPU/JDK/compiler/flags quyết định khả dụng.

**3.** Intrinsic và inlining khác nhau ở đâu?  
**Đáp án:** Inlining mở body callee vào caller; intrinsic dùng VM-known specialized implementation.

**4.** Tại sao CPU bitcount khác nhau giữa x86 và ARM vẫn cho cùng Java result?  
**Đáp án:** Java API semantics cố định, machine instruction sequence do backend lựa chọn.

**5.** `Math.fma` khác `a*b+c` ở điểm nào?  
**Đáp án:** Fused rounding semantics có thể khác hai rounding steps.

**6.** CRC32 và CRC32C của `123456789` có giống nhau?  
**Đáp án:** Không: lần lượt `cbf43926` và `e3069283`.

**7.** Nếu arraycopy copy String rồi gặp Integer không phù hợp với String[] thì sao?  
**Đáp án:** Prefix hợp lệ có thể đã được copy; sau đó ném `ArrayStoreException`.

**8.** `UseCRC32Intrinsics=true` có chứng minh JIT dùng CPU CRC không?  
**Đáp án:** Không; cần xác nhận call site và compiled code.

**9.** JVM thiếu hardware AES extension có bắt buộc Java AES API không chạy?  
**Đáp án:** Không; implementation/provider có thể dùng software path phù hợp.

**10.** Tại sao số liệu intrinsic benchmark dễ sai khi input constants?  
**Đáp án:** JIT có thể constant-fold hoặc loại công việc, không đo thao tác thực.

**11.** Cùng CPU nhưng hai JDK releases có thể khác intrinsic availability không?  
**Đáp án:** Có, do VM source, policies, flags, library và compiler thay đổi.

**12.** Cách kiểm chứng CPU instructions thực tế?  
**Đáp án:** Xem compiled-code disassembly/profiling phù hợp trên đúng VM/JDK, không chỉ Java stdout hoặc `javap`.

## 19. Tài liệu tham khảo

- [OpenJDK — IntrinsicCandidate.java](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/jdk/internal/vm/annotation/IntrinsicCandidate.java): annotation nội bộ, điều kiện không bảo đảm intrinsic và cách giữ semantics.
- [OpenJDK HotSpot — vmIntrinsics.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/vmIntrinsics.hpp): intrinsic IDs, controls và feature dependence.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): UseAES/CRC32/CRC32C/SHA/FMA/MathExact flags, UnlockDiagnosticVMOptions, PrintCompilation và PrintInlining.
- [OpenJDK HotSpot — globals.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/globals.hpp): implementation flags; nhánh master có thể khác bản JDK đang chạy.
- [Java SE 25 — System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)): checks, overlap và partial-copy behavior.
- [Java SE 25 — Math.fma](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#fma(double,double,double)): fused multiply-add semantics.
- [Java SE 25 — Integer.bitCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#bitCount(int)): bit count result contract.
- [Java SE 25 — CRC32](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/CRC32.html) và [CRC32C](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/CRC32C.html): hai checksum algorithms khác nhau.
- [Java SE 25 — Arrays.mismatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#mismatch(byte[],byte[])): index khác đầu tiên.
- [Java SE 25 — MessageDigest](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html): algorithm/provider behavior.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): đo hiệu năng JVM sau warmup có kiểm soát.

**Kết luận:** Intrinsic là cách HotSpot **có thể** thực thi method thông qua implementation đặc biệt, khai thác VM/compiler knowledge hoặc CPU ISA. Khả năng thực tế phụ thuộc **CPU, JDK release, VM implementation, provider, flags và JIT state**, nhưng **kết quả, exceptions và các ràng buộc Java API không được đổi**. Không nhầm intrinsic với inlining, JNI, vectorization hay một opcode duy nhất; không suy từ source code, bytecode hoặc một flag đã bật rằng CPU thực sự chạy intrinsic tương ứng.