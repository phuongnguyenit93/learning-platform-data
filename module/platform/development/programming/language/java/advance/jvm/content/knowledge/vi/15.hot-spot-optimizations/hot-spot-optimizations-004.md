# Tối ưu vòng lặp và loại kiểm tra dư thừa trong điều kiện phù hợp

## 1. Vấn đề: Java phải an toàn, nhưng không nhất thiết kiểm tra lại cùng một điều ở mọi vòng lặp

Vòng lặp trên mảng là một trong những đoạn mã thường xuyên được thực thi trong Java. Ở mức ngữ nghĩa, mỗi lần truy cập `a[i]` phải tuân thủ quy tắc **không được đọc mảng null** và **index phải nằm trong `[0, a.length)`**. Nếu vi phạm, chương trình phải cho thấy ngoại lệ thích hợp (`NullPointerException` hoặc `ArrayIndexOutOfBoundsException`) theo hành vi Java. Nhưng nếu compiler có thể **chứng minh** một tập kiểm tra là dư thừa, nó có thể không cần thực hiện tất cả những lần kiểm tra đó trong mã máy tối ưu.

Ví dụ:

~~~java
static long sum(int[] a) {
    long result = 0;
    for (int i = 0; i < a.length; i++) {
        result += a[i];
    }
    return result;
}
~~~

Đây là **mảnh phương thức minh họa**, không có `main`. Về logic:

- `i` bắt đầu từ `0`.
- Điều kiện tiếp tục `i < a.length` cung cấp giới hạn trên của index.
- `i` tăng đúng một đơn vị.
- Độ dài của **một array object** không đổi trong suốt lifetime của array.
- Nếu `a` là `null`, việc lấy `a.length` vẫn phải thất bại đúng quy tắc Java.

Một HotSpot **C2** đủ điều kiện có thể tận dụng hình dạng này để giảm hoặc loại **array bounds checks** trong phần thân của một đường thực thi đã được chứng minh an toàn. Đây là ví dụ điển hình của **Range Check Elimination (RCE)** — loại kiểm tra biên mảng dựa trên phân tích phạm vi chỉ số.

**Điều phải nhớ:** tối ưu là quyền của JVM implementation, **không phải lời hứa ngôn ngữ Java**. Bytecode vẫn thường có `iaload`/`iastore`; JVM phải giữ **hành vi quan sát được** như giá trị, ngoại lệ, tác dụng phụ và thứ tự hợp lệ. `javap` cho biết bytecode, **không chứng minh** native code vẫn chứa mọi kiểm tra trước khi đọc mảng.

## 2. Những kiểm tra nào thường xuất hiện trong đường chạy nóng?

| Kiểm tra / điều kiện | Vì sao có? | Khi nào có thể được tối ưu? |
| --- | --- | --- |
| **Null check** với array/object | `a.length`, `a[i]`, method call trên null phải theo semantics NPE | Khi non-null đã được chứng minh, hoặc JVM dùng một implicit null check hợp lệ |
| **Array bounds check** | `i` phải thuộc `[0, a.length)` | Khi compiler chứng minh cả miền lặp hợp lệ hoặc tạo guard/slow path thích hợp |
| **Loop termination check** | Xác định còn iterations hay không | Có thể giảm tần suất qua unrolling hoặc xử lý counted-loop |
| **Loop-invariant branch** | Ví dụ `if (enabled)` không đổi giữa các iterations | Hoist hoặc **loop unswitching** nếu hữu ích và hợp lệ |
| **Repeated arithmetic** | Ví dụ tính một biểu thức chỉ phụ thuộc dữ liệu không đổi | Loop-invariant code motion, common subexpression elimination |
| **Type/subtype check** | Đa hình, array store check với reference arrays | Có thể được bỏ nếu type information/proofs đủ mạnh |
| **Synchronization và memory effects** | Java Memory Model và trạng thái shared giữa threads | Không được di chuyển trái semantics; `volatile`/locks là ràng buộc thực |

Không phải mọi kiểm tra đều là ứng viên tối ưu. Một thao tác `getInt` trên buffer, một `List.get(i)` với danh sách có thể thay đổi kích thước, một method call có side effect hoặc một chỉ số tính qua overflow có thể đòi phân tích khác hẳn array counted-loop cơ bản.

### “Loại kiểm tra” không có nghĩa tắt an toàn

Tối ưu đúng phải đảm bảo **mọi input hợp lệ và không hợp lệ** vẫn biểu hiện theo contract Java. Một đoạn code chạy nhanh với input hợp lệ không cho phép JVM đọc `a[-1]` hoặc `a[a.length]` tùy tiện. Nếu compiler chọn một **fast path** có ít checks, nó phải chứng minh đường đó an toàn hoặc bảo toàn **guard, uncommon trap, deoptimization và slow path** khi giả định không đúng.

Đó là lý do RCE không tương đương với tự viết native pointer arithmetic bỏ biên kiểm tra.

## 3. Counted loop: hình dạng dễ cho C2 phân tích

Một **counted loop** có induction variable, điểm bắt đầu, giới hạn, bước tăng/giảm và số iterations mà compiler có thể suy ra trong điều kiện thích hợp.

~~~java
for (int i = 0; i < n; i++) {
    use(i);
}
~~~

Mảnh này chỉ minh họa, `n` và `use` được xác định ở nơi khác. Trên lý thuyết dễ suy luận:

- `init = 0`
- `limit = n`
- `stride = +1`
- miền chỉ số là `0 .. n-1` khi `n > 0`.

Nhưng **không phải cứ thấy `for` là compiler có counted loop hoàn chỉnh**. Lời gọi `use`, `break`, `continue`, side effects, overflow, giới hạn biến động, nested loops, sự phức tạp của control-flow graph và lợi ích thực tế đều ảnh hưởng.

Đối chiếu ba hình dạng:

~~~java
// A: chỉ số bám theo array length; dễ chứng minh.
for (int i = 0; i < a.length; i++) {
    total += a[i];
}

// B: cận truyền từ bên ngoài; có thể cần guard.
for (int i = from; i < to; i++) {
    total += a[i];
}

// C: chỉ số phụ thuộc giá trị dữ liệu, khó suy ra phạm vi.
for (int i = 0; i < positions.length; i++) {
    total += a[positions[i]];
}
~~~

Các đoạn trên là minh họa trong method có `a`, `positions`, `total`, `from`, `to`. Với A, chứng minh `0 ≤ i < a.length` rõ ràng. Với B, nếu không bảo đảm `from ≥ 0` và `to ≤ a.length`, JVM phải giữ hành vi lỗi khi phạm vi thực sự vượt mảng. Với C, compiler không thể suy ra mọi phần tử `positions[i]` hợp lệ chỉ từ `i < positions.length`; kiểm tra `a[positions[i]]` thường vẫn quan trọng.

**Điều kiện then chốt:** miền giá trị của **biểu thức index thực sự** phải được chứng minh nằm trong miền hợp lệ của **mảng thực sự được truy cập**.

## 4. Range Check Elimination (RCE) diễn ra theo ý tưởng nào?

Một cách suy luận ở mức cao:

1. Nhận diện induction variable và miền lặp.
2. Thu thập các array accesses, ví dụ `a[i]`, `a[i+1]`, `b[2*i]`.
3. Suy ra **điều kiện** để các indices đều hợp lệ cho cả phần lặp có thể tối ưu.
4. Chứng minh các điều kiện từ loop bounds/array lengths hoặc đặt **guards** bảo vệ fast path.
5. Chuyển/loại các kiểm tra lặp lại ở đường đã được chứng minh an toàn.
6. Giữ slow path, pre/post loop, traps hoặc deoptimization nếu đường chung không đáp ứng chứng minh.

Sơ đồ khái niệm:

~~~text
Original loop
  mỗi iteration: test loop limit, access a[i] → runtime bounds semantics
                          |
                          v
C2 phân tích induction variable và array length
                          |
               miền chỉ số chắc chắn hợp lệ?
                   /                   \
                 Có                   Chưa chứng minh được
                 |                          |
       Đường tối ưu có thể            Giữ checks, tạo guards,
       bỏ check trong body            tách loop hoặc fallback
                          |
             Cả hai phải có cùng semantics Java
~~~

**RCE là khả năng của tối ưu C2, không phải tuyên bố JVM luôn xóa đúng N lệnh.** HotSpot có nhiều pass tương tác: loop optimization, loop predication, range-check analysis, IGVN, inlining, alias analysis, unrolling và backend instruction selection.

### 4.1. Với array length cố định, cái gì thật sự “bất biến”?

`a.length` không đổi cho một array object đã xác định. Nhưng **biến reference `a` có thể được gán lại trong mã**, hoặc một field chứa array có thể bị code khác thay đổi. Compiler không được tùy tiện hoist length check của **object A** rồi dùng nó như thể luôn là length của **object B**.

~~~java
for (int i = 0; i < holder.values.length; i++) {
    consume(holder.values[i]);
}
~~~

Ở đây `holder.values` là một field, `consume` là method minh họa. Nếu object field có thể đổi giữa các lần đọc, việc biến nó thành một local snapshot **có thể thay đổi semantics**, nhất là dưới concurrency hoặc side effects. C2 chỉ được loại các loads/checks mà nó có đủ chứng minh về memory effects và aliasing theo Java Memory Model.

Với API cho phép snapshot, lập trình viên có thể chủ động viết:

~~~java
int[] local = holder.values;
for (int i = 0; i < local.length; i++) {
    consume(local[i]);
}
~~~

Đây là một **thiết kế ngữ nghĩa khác**: cố ý chốt reference cho cả loop. Không nói hai đoạn luôn tương đương nếu `holder.values` có thể bị thay đổi.

### 4.2. Với cận ngoài, proof được đặt ở đâu?

Giả sử:

~~~java
static long sumRange(int[] a, int from, int to) {
    long sum = 0;
    for (int i = from; i < to; i++) {
        sum += a[i];
    }
    return sum;
}
~~~

Không thể giả định `from` và `to` luôn hợp lệ. Nếu `from = -2` hoặc `to > a.length`, ít nhất một iteration có thể truy cập index ngoài mảng và phải tuân thủ AIOOBE tương ứng. HotSpot có thể tìm đường xử lý phổ biến với điều kiện được bảo vệ, nhưng không đơn giản bỏ kiểm tra cho mọi input.

Vì vậy, nếu **API contract** xác định rõ phạm vi hợp lệ, hãy diễn đạt rõ và kiểm tra ở boundary. Tuy nhiên, xem mục 8: thêm explicit validation **có thể thay đổi ngoại lệ và thứ tự tác dụng phụ** so với phiên bản ban đầu.

## 5. Loop predication: chuyển điều kiện ra trước vòng lặp

**Loop predication** là một kỹ thuật HotSpot C2 có thể tạo **predicate/guard** ở đường đi vào loop, thay vì giữ cùng kiểu kiểm tra bất biến trong mọi iteration. Ý tưởng quan sát được từ tài liệu OpenJDK: với index affine kiểu `i * scale + offset`, có thể lập điều kiện về start, limit, stride và array length để lựa chọn đường tối ưu an toàn.

Một minh họa khái niệm:

~~~text
Input: a, from, to

Nếu chứng minh được miền index của body nằm trong [0, a.length):
    Fast loop: tiếp tục với ít range checks trong body
Nếu không:
    Fallback giữ semantics, có thể dùng trap/deoptimization hoặc slow loop
~~~

Đoạn pseudo-code chỉ giải thích ý tưởng; **không phải** mã Java có thể dùng để cài RCE bằng tay.

### Speculative guard và uncommon trap

JIT có thể chuyên biệt hóa native code cho profile đã quan sát: ví dụ các lần gọi nóng thường có `from=0` và `to=a.length`. Một predicate có thể bảo vệ giả định về miền index; nếu điều kiện không còn đúng, JVM cần giữ khả năng thực thi code tổng quát, có thể chuyển về interpreter hoặc compiler tier khác bằng **deoptimization**.

**Không nên nghĩ “deoptimization là bug”.** Đó là cơ chế để speculative optimization vẫn bảo toàn semantics Java khi profile thay đổi.

**Không phải mọi guard failure đều cần tạo Java exception ngay tại guard.** JVM có thể chuyển về đường thực thi tổng quát rồi thực hiện các thao tác theo thứ tự source để xác định có exception thật hay không.

### Tránh nhầm guard với manual validation

**Compiler guard** là bước tối ưu hóa nội bộ và bắt buộc giữ hành vi quan sát được của chương trình. **Manual validation** do người viết mã thêm có thể chủ động thay đổi contract API; đó là thay đổi ở tầng source.

Vì vậy câu “đưa mọi array bounds check ra đầu method” **không tự đúng** nếu trong source có I/O, side effects, `break` hoặc chỉ một phần loop có thể chạy.

## 6. Loop peeling, pre/main/post và ranh giới chỉ số

Một loop có thể có vùng đầu/cuối khó bảo đảm an toàn cho mọi iteration nhưng có vùng giữa chắc chắn hợp lệ. JVM có thể **peel/split** loops:

~~~text
Source:
 for i = begin ... end:
    use(a[i + 1])

Một tổ chức native khả dĩ:
 [pre-loop]      xử lý vài iteration đầu / checks cần thiết
 [main-loop]     miền chứng minh an toàn, checks được giảm
 [post-loop]     xử lý phần dư / tail với checks cần thiết
~~~

Đây là sơ đồ, **không cam kết** C2 sẽ luôn tạo đúng ba loops. Việc tách loop làm code lớn hơn và có overhead của branches/guards; với loops rất ngắn, tối ưu ấy có thể **không đáng**.

Ví dụ index `i + 1` đòi chứng minh `0 ≤ i + 1 < a.length`. Chỉ vì điều kiện `i < a.length` đúng **chưa đủ** chứng minh `i+1` hợp lệ ở iteration cuối. Người học cần nhìn **index expression**, không chỉ loop condition.

Trường hợp có hai arrays:

~~~java
for (int i = 0; i < a.length; i++) {
    sum += a[i] + b[i];
}
~~~

`a[i]` có bound theo `a.length`; còn `b[i]` chỉ hợp lệ mọi vòng nếu `b` đủ dài. Điều kiện an toàn thêm có thể là `b != null` và `b.length >= a.length`. JVM không được âm thầm bỏ check của `b[i]` khi `b` ngắn hơn.

## 7. Các biến đổi loop khác thường đi cùng RCE

### 7.1. Loop-invariant code motion — LICM

Một biểu thức chỉ phụ thuộc dữ liệu không đổi trong suốt loop, không có side effect hoặc ràng buộc thứ tự exception/memory cần giữ, có thể được dời ra ngoài loop.

~~~java
int scale = config.scale();
for (int i = 0; i < a.length; i++) {
    result += a[i] * scale;
}
~~~

Đoạn này đã chủ động gọi `config.scale()` **trước loop**. Nếu source ban đầu gọi `config.scale()` **bên trong loop**, tự dời call ra ngoài chỉ hợp lệ khi lời gọi không có side effects, không thay đổi giá trị, và việc thay đổi số lần/thời điểm gọi không đổi semantics. Với `volatile`, locks, I/O hoặc stateful method, không được tùy tiện hoist.

**LICM giảm work lặp lại nếu an toàn**, nhưng đôi khi làm tăng register pressure hoặc thực hiện một phép tính trước loop dù loop có zero iterations; compiler phải xét tính hợp lệ và lợi ích.

### 7.2. Loop unswitching

Nếu có nhánh **không thay đổi theo iteration**:

~~~java
for (int i = 0; i < a.length; i++) {
    if (enabled) {
        sum += a[i];
    }
}
~~~

C2 có thể tạo hai phiên bản loop:

~~~text
if (enabled):
    for (...) sum += a[i]
else:
    for (...) [body khác hoặc không có cập nhật sum]
~~~

Ý tưởng: chỉ kiểm tra `enabled` một lần thay vì ở mỗi iteration. Nhưng duplication tăng code size, có thể tác động instruction cache. **Không hứa C2 luôn unswitch**; JIT dùng cost model/compile budget. Nếu `enabled` là giá trị có thể thay đổi theo iteration (ví dụ `volatile` đọc lại), không được coi nó là invariant vô điều kiện.

### 7.3. Loop unrolling

Unrolling sao chép body nhiều lần:

~~~text
Ban đầu:
  for i: process(a[i])

Sau unroll 4:
  xử lý a[i], a[i+1], a[i+2], a[i+3]
  rồi i += 4
  phần còn dư dùng tail path
~~~

Lợi ích có thể gồm ít branch overhead và nhiều cơ hội instruction-level parallelism/RCE/vectorization. Nhưng body lớn hơn làm code cache/instruction cache chịu áp lực; loop quá ngắn hoặc body phức tạp có thể không lợi.

**Không được bỏ phần dư:** nếu array length = 9 và unroll factor = 4, chương trình vẫn phải xử lý đúng 9 elements (ví dụ 4 + 4 + 1), không đọc tới element thứ 12.

### 7.4. Auto-vectorization / SuperWord

Sau khi C2 thấy những operations trên các phần tử lân cận độc lập, có thể dùng SIMD instructions để xử lý nhiều dữ liệu cùng lúc; HotSpot có **SuperWord** vectorization. Không phải loop Java nào có array cũng vectorize.

Điều kiện/rào cản điển hình:

- Truy cập memory đều đặn/contiguous với dependencies đủ rõ.
- Không có aliasing gây sai thứ tự đọc/ghi.
- Phép toán có semantics cho phép vectorize (chú ý floating point, strict ordering, overflow và reductions).
- Hardware/CPU instruction set hỗ trợ và VM flags phù hợp.
- Không có branch/call/exception ordering khiến vectorized path sai.

**SIMD không đồng nghĩa Java Vector API**. Auto-vectorization là JIT optimization; Java Vector API ở Java 17 là incubator module và không phải phần phụ thuộc của các code mẫu trong bài.

### 7.5. Induction-variable simplification

C2 có thể canonicalize biểu thức index, loại các phép tính có thể suy ra từ induction variable và thay phép nhân lặp lại bằng increments nếu đúng semantics. Nhưng với `int` arithmetic, Java overflow **wrap quanh modulo 2^32**, nên không được thay đổi logic vòng lặp chỉ bằng trực giác số học vô hạn.

### 7.6. Common subexpression elimination

Nếu hai phép tính giống nhau dùng operands không thay đổi, không có memory aliasing hoặc side effects cần xét, compiler có thể dùng lại kết quả thay vì tính lại. Với array loads, phải xem **có store hoặc call nào có thể thay đổi data giữa hai lần đọc hay không**.

## 8. Cẩn thận: Java exceptions và side effects không được đổi chỗ tùy tiện

Xét một phương thức mô tả:

~~~java
static int useRange(int[] a, int from, int to) {
    int sum = 0;
    for (int i = from; i < to; i++) {
        System.out.println("VISITED=" + i);
        sum += a[i];
    }
    return sum;
}
~~~

Nếu `a.length=3`, `from=1`, `to=5`, source sẽ in các dòng `VISITED=1`, `VISITED=2` và `VISITED=3` trước khi truy cập `a[3]` ném `ArrayIndexOutOfBoundsException`. Nếu lập trình viên chuyển **toàn bộ validation** lên đầu method và ném ngay khi `to> a.length`, các `println` trước lỗi sẽ biến mất.

Đây là **thay đổi hành vi quan sát được**. C2 cũng không được tối ưu làm mất những side effects phải xảy ra trước exception theo semantics Java.

Một cách xây dựng API khác hoàn toàn hợp lệ:

~~~java
Objects.checkFromToIndex(from, to, a.length);
for (int i = from; i < to; i++) {
    process(a[i]);
}
~~~

Nhưng **đó là một API contract mới có kiểm tra upfront**, không tự tương đương với mọi code cũ, đặc biệt khi loop không có iterations hoặc khi có side effects/exception order. `Objects.checkFromToIndex` là API Java 9+, dùng được trên Java 17.

### Trường hợp loop zero iterations

Nếu:

~~~java
for (int i = 0; i < 0; i++) {
    sum += a[i];
}
~~~

Body không được chạy; nếu `a` là null, đoạn loop này **không nhất thiết NPE** vì không có lần dereference bên trong body. Nhưng nếu đổi thành `Objects.requireNonNull(a);` trước loop, nó sẽ ném NPE ngay.

Ngược lại, điều kiện `i < a.length` **có dereference `a` ngay khi kiểm tra condition**, dù body không chạy nếu length bằng 0. Từng biểu thức trong điều kiện mới quyết định semantics.

### Range check elimination không cho phép “bỏ qua ngoại lệ hiếm”

Nếu index out-of-range xuất hiện ở production, Java phải tiếp tục ném đúng lỗi khi code thực hiện invalid access. JIT có thể dùng guard và fallback thay vì giữ check trong hot body, nhưng **không được bỏ validation theo kiểu native unsafe**.

## 9. Mẫu Java 17 runnable: miền index rõ và đầu ra xác định

Tạo file **`LoopOptimizationDemo.java`**:

~~~java
import java.util.Objects;

public final class LoopOptimizationDemo {
    static long sumRange(int[] values, int from, int to) {
        Objects.requireNonNull(values, "values");
        Objects.checkFromToIndex(from, to, values.length);
        long total = 0;
        for (int i = from; i < to; i++) {
            total += values[i];
        }
        return total;
    }

    static long sumIfEnabled(int[] values, boolean enabled) {
        long total = 0;
        for (int i = 0; i < values.length; i++) {
            if (enabled) {
                total += values[i];
            }
        }
        return total;
    }

    static long sumShifted(int[] values) {
        long total = 0;
        for (int i = 0; i + 1 < values.length; i++) {
            total += values[i + 1];
        }
        return total;
    }

    static int firstAtLeast(int[] values, int threshold) {
        for (int i = 0; i < values.length; i++) {
            if (values[i] >= threshold) {
                return i;
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] a = {3, 5, 7, 11, 13, 17};
        System.out.println("full=" + sumRange(a, 0, a.length));
        System.out.println("middle=" + sumRange(a, 1, 5));
        System.out.println("empty=" + sumRange(a, 4, 4));
        System.out.println("enabled=" + sumIfEnabled(a, true));
        System.out.println("disabled=" + sumIfEnabled(a, false));
        System.out.println("shifted=" + sumShifted(a));
        System.out.println("firstAtLeast12=" + firstAtLeast(a, 12));
        try {
            sumRange(a, 2, 7);
            System.out.println("unexpected");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("badRangeRejected=true");
        }
        try {
            sumRange(null, 0, 0);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 LoopOptimizationDemo.java
java LoopOptimizationDemo
~~~

**Stdout đã biên dịch/chạy kiểm chứng trên HotSpot/OpenJDK 24 với target Java 17:**

~~~text
full=56
middle=36
empty=0
enabled=56
disabled=0
shifted=53
firstAtLeast12=4
badRangeRejected=true
nullRejected=true
~~~

### Phân tích đúng phạm vi

- `sumRange`: `Objects.checkFromToIndex` kiểm tra **contract range `[from,to)`** trước khi loop. Trong phạm vi hợp lệ, counted-loop có giới hạn rõ, thuận lợi cho optimizer suy ra `from ≤ i < to ≤ values.length`.
- `sumIfEnabled`: `enabled` là parameter không bị gán lại trong method nên là một loop-invariant candidate. C2 **có thể** unswitch hoặc tối ưu đường false, nhưng kết quả `enabled=56`/`disabled=0` **không chứng minh native code đã unswitch**.
- `sumShifted`: điều kiện `i+1 < values.length` bảo vệ index thực sự `i+1`; tổng 53 là 56 trừ phần tử đầu tiên 3. Việc viết rõ boundary giúp code dễ review.
- `firstAtLeast`: có `return` giữa loop. Nếu threshold 12, phần tử đầu tiên đạt là 13 ở index 4. Việc có early exit có thể giảm cơ hội vectorize hoặc một số loop transformations; không khẳng định C2 sẽ từ chối mọi optimization.
- Invalid range bị từ chối trước loop bằng `Objects.checkFromToIndex`; method ném subtype `IndexOutOfBoundsException`, được catch ở main.
- `null` bị từ chối bởi `Objects.requireNonNull` kể cả khi `[from,to)` rỗng. Đó là lựa chọn rõ ràng của API này, không phải behavior mặc định của mọi loop Java.

**Chú ý:** chương trình chỉ gọi mỗi method vài lần, thường **chưa đủ** để C2 JIT compile chúng. Output này kiểm tra **semantics**, không phải đo RCE throughput hay bằng chứng có vector instructions.

## 10. Phương thức kiểm tra và tối ưu ở hai tầng khác nhau

### `javap` nhìn thấy bytecode, không nhìn thấy C2 native machine code

Sau khi biên dịch:

~~~bash
javap -classpath . -c -p LoopOptimizationDemo
~~~

Bạn sẽ thường thấy các instructions như `arraylength`, `iaload`, `iinc`, `if_icmpge`, `goto`, và các lời gọi `Objects.checkFromToIndex` trong bytecode tương ứng.

Ví dụ logic:

~~~text
arraylength   → lấy độ dài array
if_icmpge     → nhảy khi index vượt giới hạn loop
iaload        → đọc int element theo index
iinc          → tăng induction variable
goto          → backedge vòng lặp
~~~

`javap` không cho biết compiler C2 đã loại implicit bounds check trong **native code** hay chưa. Đây là lỗi chẩn đoán thường gặp: thấy `iaload` trong bytecode rồi kết luận “mỗi iteration vẫn phải chạy y nguyên array bounds check” là suy luận quá xa.

### Code JIT có thể thay đổi trong cùng JVM process

Ban đầu method interpreted, rồi C1, sau đó C2 hoặc lại deoptimize/recompile. Một benchmark bắt đầu đo ngay từ lần đầu có thể cộng **compilation/profiling** vào thời gian chạy và đưa ra kết luận khác steady state.

## 11. Java 17 runnable: tạo hot loop và xem JIT compilation log

Tạo file **`LoopWarmupProbe.java`**:

~~~java
public final class LoopWarmupProbe {
    private static volatile long published;

    static long sumArray(int[] values) {
        long sum = 0;
        for (int i = 0; i < values.length; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {3, 5, 7, 11, 13, 17};
        long checksum = 0;

        for (int k = 0; k < 100_000; k++) {
            checksum += sumArray(values);
        }

        published = checksum;
        System.out.println("rounds=100000");
        System.out.println("checksum=" + published);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 LoopWarmupProbe.java
~~~

Chạy thông thường:

~~~bash
java LoopWarmupProbe
~~~

**Stdout cố định:**

~~~text
rounds=100000
checksum=5600000
~~~

Vì mỗi lượt cộng `3+5+7+11+13+17 = 56`, 100.000 lượt cho 5.600.000. Kết quả đã được thực sự chạy với JDK 24 target Java 17.

Bật HotSpot diagnostic printing:

~~~bash
java -XX:+PrintCompilation LoopWarmupProbe
~~~

**Một quan sát thực tế** khi chạy trên HotSpot 24 có các compilation lines liên quan:

~~~text
LoopWarmupProbe::sumArray ... level 3
LoopWarmupProbe::sumArray ... level 4
LoopWarmupProbe::main ... OSR/normal compilation
~~~

Ba dòng trên là **tóm tắt ý nghĩa của diagnostic output**, không phải sao chép nguyên văn format JVM. Compilation IDs, timings, flags và tier activity có thể khác ở Java 17, OS và các runs. Trong lần thử, JVM thực sự ghi nhận `sumArray` ở compilation level 3 rồi level 4; điều này chứng minh nó được **biên dịch**, **không tự chứng minh** cụ thể bao nhiêu range checks bị loại trong native code.

### `-Xint` để đối chiếu semantics

~~~bash
java -Xint LoopWarmupProbe
~~~

Interpreter-only vẫn in **cùng** `rounds=100000` và `checksum=5600000`. Đây là kiểm tra hành vi. **Không biến một lần chạy `-Xint` so với JIT thành kết luận speedup có giá trị production**: đo thời gian cần warm-up/forks, nhiều samples và tránh loại work.

### Không đồng nhất `PrintCompilation` với `PrintInlining`

Trên HotSpot, `-XX:+PrintCompilation` cho biết những compilation events, còn `-XX:+PrintInlining` có thể cần unlock diagnostic options:

~~~bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintInlining -XX:+PrintCompilation \
     LoopWarmupProbe
~~~

Đây là cú pháp Bash. Các logs có thể lớn và tạo overhead. `PrintInlining` cho biết quyết định **inlining** chứ **không phải** một báo cáo đầy đủ, chính thức rằng bounds-check elimination thành công.

## 12. Chứng minh native optimization khó hơn nhìn latency

Có những mức bằng chứng khác nhau:

| Mức | Bằng chứng | Có thể kết luận? |
| --- | --- | --- |
| 1 | Code vẫn trả đúng khi `java` hoặc `java -Xint` | **Semantics** đúng trên inputs đã thử |
| 2 | `javap -c -p` cho thấy `iaload`, loop branches | **Bytecode** có array operation; chưa biết optimized native code |
| 3 | `-XX:+PrintCompilation` có C2 level 4 | Hot method có native compilation; chưa biết RCE/LICM/unswitch riêng |
| 4 | JFR/method profiler cho thấy thời gian/counter thay đổi | Có khác biệt hiệu năng quan sát được; chưa biết biến đổi nào gây ra |
| 5 | Phân tích C2 Ideal graph/assembly (nếu công cụ và build hỗ trợ) | Có thể khảo sát guards/checks/vector ops trong **compiled version** cụ thể |
| 6 | Benchmark đúng phương pháp với nhiều forks/inputs và profiling | Có dữ liệu để đánh giá hiệu năng, nhưng không suy ra codegen y hệt trên mọi JVM |

**Assembly/Ideal graph không mặc định có sẵn.** Tùy HotSpot build, việc in disassembly có thể cần `hsdis` hoặc công cụ chuyên biệt. Các flags `TraceLoopOpts`/`TraceLoopPredicate` trong source HotSpot có thể là **develop-only** và không chạy trong product release builds; không dán tùy tiện vào production JVM rồi hứa nó luôn hỗ trợ.

### Phân tích C2 graph

OpenJDK có source liên quan `opto/loopnode.cpp`, `loopTransform.cpp`, `loopPredicate.cpp` và compiler flags. Tuy nhiên cấu trúc source thay đổi theo JDK branch. Đọc code giúp hiểu thuật toán, nhưng muốn chứng minh phiên compiled method cụ thể phải kiểm tra build/flags/profile tương ứng.

Dấu hiệu JIT loop optimization trong assembly/IR cần xem gồm:

- Có còn array bounds comparison cho **mỗi iteration** trong main loop không?
- Có **pre-loop/guard/predicate** thay cho checks per element không?
- Có tail loop sau unrolling/vectorization để xử lý remainder không?
- Null/bounds guard có tồn tại ở fast path entrance hay fallback không?
- Deoptimization entry/uncommon trap bảo vệ assumptions nào?
- Code compiled version đó có thực sự được dùng trong workload đo không?

**Không đủ** chỉ nhìn một loop máy không có nhánh so sánh mà bỏ qua prologue, versioning guard hoặc uncommon trap ở địa chỉ khác.

## 13. Rào cản thường gặp đối với RCE, LICM và vectorization

### 13.1. Biểu thức index không tuyến tính hoặc phụ thuộc dữ liệu

~~~java
for (int i = 0; i < indexes.length; i++) {
    total += values[indexes[i]];
}
~~~

`i` hợp lệ cho `indexes`, nhưng `indexes[i]` có thể là bất kỳ `int`, kể cả âm hoặc quá `values.length`. Một optimizer không được bỏ bounds check cho `values[indexes[i]]` trừ khi có proof/phạm vi thích hợp.

### 13.2. Thay đổi references hoặc aliasing

~~~java
for (int i = 0; i < holder.data.length; i++) {
    callback(holder);
    sum += holder.data[i];
}
~~~

`callback` có thể thay `holder.data`, cập nhật state hoặc throw. Không được coi `holder.data` luôn trỏ cùng mảng. Nếu muốn contract snapshot, thay đổi source một cách có ý thức và kiểm tra thread safety.

### 13.3. Volatile và synchronization

Đọc `volatile` hoặc vào/ra `synchronized` có memory ordering semantics; JIT không được bỏ các lần đọc/ghi cần thiết rồi nói “giá trị hầu như không đổi”. Với parameter `boolean enabled` không bị thay đổi, unswitch có thể phù hợp hơn so với `volatile boolean enabled` được đọc trong loop.

### 13.4. Side effects trước truy cập có thể ném exception

Nếu `log(i)` hoặc `counter++` cần xảy ra trước lần array access lỗi, không thể chuyển hết validation lên đầu để ném trước những side effects ấy mà vẫn gọi hai source versions tương đương.

### 13.5. Early exits và exception paths

`break`, `continue`, `return`, `throw` giữa loop có thể tạo control-flow phức tạp, hạn chế một số biến đổi. Không tuyên bố “có `break` thì JIT không tối ưu” — thực tế có thể tối ưu một phần.

### 13.6. Overflow trong induction variable

Với `int` cộng/trừ theo semantics Java, các giá trị có thể overflow. Ví dụ **không an toàn**:

~~~java
for (int i = start; i <= end; i++) {
    process(i);
}
~~~

Nếu `end == Integer.MAX_VALUE` và loop đạt `i == MAX_VALUE`, `i++` wrap về `Integer.MIN_VALUE` rồi điều kiện `i <= end` tiếp tục đúng; loop có thể không kết thúc. Đây không chỉ là chuyện hiệu năng mà là **logic bug**.

Với cấu trúc có khả năng chạm integer maximum, nên thiết kế cận và kiểu index phù hợp, tránh overflow hoặc dùng loop exit condition đã chứng minh an toàn. **Không sửa máy móc `<=` thành `<`** nếu điều đó làm bỏ phần tử cuối mà business cần.

### 13.7. Floating-point reductions

Tổng `double` qua các iterations có thể không associative theo IEEE 754; reorder hoặc vectorize reductions phải tuân theo các ràng buộc floating-point semantics của Java version/VM. Không mặc định C2 được tự do thay đổi thứ tự cộng như với số thực toán học lý tưởng.

### 13.8. Short loops và code size

Hoist/predicate/unroll có giá nhập môn, tăng code size. Một vòng chỉ 2–3 iterations có thể chạy nhanh hơn với checks đơn giản, không cần tạo nhiều versions. **Cost model** là lý do compiler đôi khi không tối ưu một loop có vẻ đủ điều kiện trên lý thuyết.

## 14. Thiết kế source hỗ trợ compiler: rõ contract, không “ép JIT”

### 14.1. Dùng cận phù hợp với dữ liệu thật

Thường nên ưu tiên:

~~~java
for (int i = 0; i < a.length; i++) {
    use(a[i]);
}
~~~

thay vì tự tính length từ một nguồn không liên quan. Điều này giúp người đọc thấy ngay miền truy cập an toàn, và cung cấp loop form dễ phân tích cho JIT.

### 14.2. Validation ở API boundary khi đó là contract mong muốn

Nếu method yêu cầu `[from,to)` hợp lệ **trước bất kỳ side effect nào**, hãy kiểm tra rõ:

~~~java
Objects.requireNonNull(a);
Objects.checkFromToIndex(from, to, a.length);
for (int i = from; i < to; i++) {
    sum += a[i];
}
~~~

`Objects.checkFromToIndex` (Java 9+) minh định API contract, giúp code an toàn và dễ review. Dù vậy, nó **không bảo đảm C2 đã loại mọi internal check**, và việc thêm validation vào một method cũ có side effects có thể đổi semantics như mục 8.

### 14.3. Dùng local reference khi contract muốn snapshot

~~~java
int[] snapshot = holder.data;
for (int i = 0; i < snapshot.length; i++) {
    process(snapshot[i]);
}
~~~

Nếu mục tiêu là xử lý **một phiên bản array reference cố định**, cách này thể hiện ý định. Nếu mục tiêu phải thấy những thay đổi field ngay trong loop, local snapshot **không tương đương**.

### 14.4. Không viết unrolling bằng tay trước khi benchmark

Thủ công viết 8 accesses mỗi vòng làm code phức tạp, dễ lỗi tail/overflow, có thể phá optimizer hoặc tốn instruction cache. Hãy để JIT có cơ hội tự làm qua canonical loop trước; chỉ manual optimize nếu có measurement/JMH + inspection chứng minh và tests bảo vệ.

### 14.5. Không giảm checks bằng `Unsafe` chỉ vì benchmarks

Chuyển Java array sang raw native pointer để bỏ bounds safety là một bước rất khác về safety/lifetime, có thể gây memory corruption. Các flags nội bộ `Unsafe`/module access không phải giải pháp chung cho một loop chậm. Tối ưu algorithm, data layout, allocation, concurrency và I/O trước khi phá contract memory safety.

## 15. Benchmark đúng cách: nóng, đo đủ lâu, tránh compiler ảo thuật

Một vòng `System.nanoTime()` bao quanh 5 iterations không đủ để kết luận `a[i]` đã được RCE. Những yếu tố gây nhiễu:

- JIT chưa đủ hot, hoặc đang đổi C1→C2/OSR.
- GC xảy ra trong khoảng đo.
- CPU turbo, thermal throttling và OS thread scheduling.
- Dữ liệu quá nhỏ, nằm toàn trong cache; memory bandwidth chưa được thử.
- JIT constant-fold hoặc dead-code eliminate một phép tính không dùng kết quả.
- Branch predictability, aliasing và vectorization phụ thuộc input shape.
- `nanoTime()` overhead chi phối work cực ngắn.
- Benchmark tool có **coordinated omission** nếu dùng cho request latency ở server.
- Ngoại lệ hiếm và slow paths không được test.

### JMH được ưu tiên cho microbenchmark

Java Microbenchmark Harness (JMH) từ dự án OpenJDK quản lý **forks, warm-up iterations, measurement iterations, state, parameterization, result consumption** và thống kê. Ví dụ mẫu cấu trúc JMH:

~~~java
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
public class SumBenchmark {
    @Param({"64", "4096"})
    public int size;

    int[] values;

    @Setup(Level.Trial)
    public void setUp() {
        values = new int[size];
        for (int i = 0; i < size; i++) values[i] = i;
    }

    @Benchmark
    public long sumRange() {
        return LoopOptimizationDemo.sumRange(values, 0, values.length);
    }
}
~~~

**Đây không phải chương trình biên dịch với `javac` trần**: cần JMH dependencies/plugin và benchmark class trong cùng package hoặc điều chỉnh visibility cho `LoopOptimizationDemo.sumRange`. `@Param` kiểm tra nhiều kích thước array thay vì chỉ một length có lợi cho compiler. JMH vẫn không thay thế end-to-end load testing với real request mix.

Không so loops chỉ từ “ns/op thấp nhất” nếu một version làm ít work hơn, bỏ exception behavior hoặc sử dụng dữ liệu có layout khác. Cần cùng correctness, cùng setup, cùng CPU/JDK flags và được warm theo điều kiện đại diện.

### Một phương pháp so A/B nghiêm túc

1. Giữ JDK build, `-Xms/-Xmx`, CPU quota và machine workload giống nhau.
2. Dùng representative lengths (0, 1, 2, 3, 64, 4096, hàng triệu phần tử).
3. Test invalid range, null, early return, dữ liệu âm/dương, overflow edge.
4. Warm-up đủ cho method/branches cần đo, kiểm chứng compilation mode bằng logs.
5. Dùng nhiều process forks độc lập, thay đổi thứ tự ứng viên khi cần.
6. Đo cả throughput/latency, errors và GC/allocation, không chỉ avg timing.
7. Nếu khẳng định **RCE thực sự**, phân tích optimized IR/native code trên build cụ thể.
8. Báo kết quả đúng giới hạn: “thử nghiệm cho thấy nhanh hơn” khác “mọi JVM đều bỏ checks”.

## 16. Những tối ưu này có còn đúng khi method bị deoptimize?

JIT code là một **implementation choice** của JVM. Nếu một guard assumption không còn đúng, HotSpot có thể **deoptimize** và tiếp tục tại bytecode-level state tương đương, sau đó interpreter hoặc compiler khác xử lý.

Một ví dụ giả định:

~~~text
Warm-up:
  99.99% calls có from=0, to=a.length, a non-null
              |
              v
C2 dùng profile/guards tạo đường tối ưu
              |
Production:
  thỉnh thoảng to>a.length
              |
              v
guard/trap/fallback phải bảo toàn ngoại lệ và side effects
              |
              v
có thể deoptimize hoặc dùng slower path
~~~

Không nói rằng `Objects.checkFromToIndex` sẽ luôn bị chuyển thành một trap, hoặc mọi invalid call chắc chắn deoptimize. Compiler có nhiều lựa chọn phụ thuộc code shape, profile và JDK build.

**Correctness được giữ ở mọi tier.** Java không cho phép chương trình cho kết quả sai chỉ vì code đã “nóng”. Đây là lý do một test chạy đúng ở JIT level 4 không phải chứng minh performance optimization cụ thể, nhưng là điều kiện cần để đánh giá đúng đắn.

## 17. Checklist khi thấy một vòng lặp Java bị chậm

- [ ] Xác định **đúng loop hot** bằng profiler, không đoán từ code review.
- [ ] Kiểm tra thuật toán O(N), data volume và memory locality trước khi đổ cho bounds checks.
- [ ] Xem source indexes: có `i`, `i+1`, `2*i`, `positions[i]` và nhiều arrays khác nhau không?
- [ ] Xem **bounds thực**: đã chứng minh trên index expression/mảng đang dùng chưa?
- [ ] Xem potential integer overflow/negative indices.
- [ ] Xem array reference có stable không, có call/side effect/volatile/aliasing trong body không?
- [ ] Xem early break/return hoặc error behavior có làm transformations bị ràng buộc không?
- [ ] Không tự move null/bounds checks ra trước side effects nếu thay đổi contract.
- [ ] Dùng `javap` hiểu bytecode; dùng compilation logs để biết JIT activity.
- [ ] Không coi `PrintCompilation` là báo cáo RCE hoặc vectorization.
- [ ] Khi cần xác nhận optimization, dùng IR/native assembly tools có build phù hợp.
- [ ] Benchmark bằng JMH, nhiều forks/iterations, representative inputs.
- [ ] Dùng `-Xint` để đối chiếu semantics khi có ích, không gọi đó là “mô phỏng cold JIT”.
- [ ] Đo cả hiệu năng và correctness của invalid/null/overflow edge cases.
- [ ] Nếu tự đổi cấu trúc loop, lưu tests so phiên bản trước/sau với nhiều random seeds.
- [ ] Giữ safe APIs trừ khi có lý do native memory thật sự và audit riêng.

## 18. Tự kiểm tra: dự đoán điều gì được tối ưu trong điều kiện phù hợp?

### Câu 1

Với `for (int i=0; i<a.length; i++) sum+=a[i]`, kiểm tra nào **có cơ hội** được giảm? **Array bounds checks** trên đường compiled đã được chứng minh an toàn, không phải nghĩa vụ bảo đảm runtime sẽ làm.

### Câu 2

`a[i+1]` với loop limit `i<a.length` có được phép bỏ check vô điều kiện không? **Không**, iteration cuối có thể truy cập quá giới hạn; cần điều kiện/một chiến lược xử lý đúng.

### Câu 3

Hai arrays `a`, `b` với loop limit `a.length` có được bỏ `b[i]` bounds check vì `a[i]` hợp lệ không? **Không**, `b` có thể ngắn hơn hoặc null; cần chứng minh riêng.

### Câu 4

`values[indexes[i]]` có thuộc counted loop dễ RCE không? **Không mặc định**, vì các giá trị trong `indexes` có thể ngoài phạm vi của `values`.

### Câu 5

Khi C2 chuyển điều kiện ra trước loop, nó có thể thay đổi ngoại lệ được ném hoặc bỏ side effects bắt buộc không? **Không**.

### Câu 6

`Objects.checkFromToIndex` có tồn tại trong Java 17 không? **Có**, từ Java 9.

### Câu 7

Nếu `checkFromToIndex(2,7,6)` ném exception trước loop, có phải JIT “đã phát hiện lỗi” không? **Không**, đó là validation do source API yêu cầu.

### Câu 8

Có `iaload` trong `javap` thì native code C2 chắc chạy một check cho mỗi `iaload` không? **Không**, bytecode khác native optimized code.

### Câu 9

`PrintCompilation` có level 4, có thể kết luận RCE đã xảy ra? **Không**, chỉ kết luận có compilation ở tier tương ứng.

### Câu 10

Loop unswitching áp dụng với `if (enabled)` khi `enabled` là parameter stable? **Có thể**, nếu compiler thấy đáng và hợp lệ.

### Câu 11

`volatile` field đọc trong body có thể bị coi không đổi suốt loop vô điều kiện không? **Không**, memory semantics có thể đòi những lần đọc.

### Câu 12

Unroll factor 4 trên array length 9 có thể bỏ phần tử cuối không? **Không**, phải có path xử lý phần dư hoặc tổ chức tương đương.

### Câu 13

RCE và auto-vectorization có phải một phép tối ưu duy nhất không? **Không**; RCE xử lý checks, vectorization kết hợp operations dùng SIMD trong điều kiện phù hợp.

### Câu 14

`-Xint` cho cùng output nhưng chậm hơn có chứng minh optimized native code đã vectorize không? **Không**.

### Câu 15

Vì sao `for (int i=start; i<=Integer.MAX_VALUE; i++)` nguy hiểm? **`int` overflow** ở lần increment, có thể khiến loop không kết thúc.

### Câu 16

Loop có `break` thì C2 chắc chắn không tối ưu gì? **Không**, có thể tối ưu một phần nhưng control flow phức tạp hơn.

### Câu 17

`holder.array` thay đổi giữa iterations, local snapshot có luôn giữ semantics cũ không? **Không**, chỉ làm vậy khi contract cho phép cố định reference.

### Câu 18

Benchmark một array dài 1 phần tử có thể kết luận tối ưu tốt cho array 1 triệu phần tử? **Không**, memory bandwidth/cache/branch và transformation profitability khác.

### Câu 19

Nếu guard giả định thất bại, compiler được phép làm gì? **Chọn fallback/deoptimization hợp lệ**, vẫn giữ Java semantics.

### Câu 20

Điều gì quan trọng nhất khi sửa code vì performance? **Đo đúng bottleneck và không thay đổi correctness**, kể cả exception ordering và side effects.

## 19. Nguồn tham khảo để đào sâu

- **Java Language Specification 17**, §15.10 Array Access Expressions (điều kiện truy cập/ngoại lệ): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.4
- **JVMS 17**, bytecode `iaload`, `iastore`, array access instructions: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- **Java SE 17 `Objects.checkFromToIndex`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#checkFromToIndex(int,int,int)
- **Oracle JDK 17 `javap` disassembler**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- **Oracle JDK 17 `java` launcher** (`-Xint`, diagnostic compilation flags, JIT tooling): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JDK 17u, HotSpot C2 compiler flags** (ví dụ LoopUnroll, UseLoopPredicate, LoopUnswitching, SuperWord): https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp
- **OpenJDK HotSpot loop optimizations** — tài liệu giải thích counted loops, loop predication và range-check elimination: https://wiki.openjdk.org/display/HotSpot/Loop+optimizations+in+Hotspot+Server+VM+Compiler+(C2)
- **Red Hat Developer, Range check elimination in loops in OpenJDK's HotSpot JVM** (2022): https://developers.redhat.com/articles/2022/03/16/range-check-elimination-loops-openjdks-hotspot-jvm
- **OpenJDK JMH** — phương pháp benchmark Java đáng tin hơn `nanoTime` vòng lặp thủ công: https://openjdk.org/projects/code-tools/jmh/

**Kết luận:** HotSpot C2 có thể cải thiện các vòng lặp bằng cách chứng minh **miền chỉ số**, loại những **array bounds/null checks dư thừa**, tạo **loop predicates**, tách **pre/main/post**, hoist những điều kiện bất biến, **unswitch**, **unroll** hoặc **vectorize** trong những điều kiện thích hợp. Nhưng **mọi bước đều bị ràng buộc bởi Java semantics**: null, giới hạn mảng, overflow, exceptions, side effects, aliasing, concurrency và điều kiện dừng phải còn đúng. Hãy viết source có contract rõ, chọn canonical loop dễ hiểu, đo bằng JMH/workload thật, và chỉ khẳng định một biến đổi JIT cụ thể sau khi xem **optimized IR/assembly** của đúng JVM build — không suy ra từ `javap`, một dòng `PrintCompilation` hoặc một lần benchmark chạy nhanh.
