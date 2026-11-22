# Đối chiếu JNI và FFM với cùng tập đầu vào, kết quả và thư viện C

Khi chuyển một tích hợp native từ **Java Native Interface (JNI)** sang **Foreign Function & Memory API (FFM)**, chỉ gọi được một hàm không đủ để khẳng định hai cách liên kết tương đương. Điều cần chứng minh là **cùng thư viện C, cùng hàm nghiệp vụ, cùng tập dữ liệu và cùng quy tắc lỗi** tạo ra kết quả giống nhau. Bên cạnh phép so sánh trực tiếp JNI–FFM, phải có **oracle độc lập** (ví dụ thuật toán Java thuần) để tránh tình huống hai đường binding cùng trả về một kết quả sai.

Bài này tạo một shared library C duy nhất trên **Linux x86-64**; JNI gọi hàm C thông qua một JNI adapter còn FFM gọi thẳng biểu tượng C đó. Chương trình Java dùng JDK **22 trở lên**, vì FFM trở thành API chuẩn trong JDK 22 (JEP 454) ở gói java.lang.foreign. JNI dùng được từ nhiều JDK trước đó; **mã FFM chuẩn ở bài này không biên dịch trên JDK 17**. Hai cách gọi đều thực thi mã native trong cùng JVM: lỗi con trỏ hoặc memory corruption từ C vẫn có thể làm sập cả process.

## 1. Định nghĩa tiêu chí “hai đường tương đương”

Cố định những biến sau trước khi viết wrapper:

1. **Một nguồn mã C:** chỉ một tệp chứa hàm nghiệp vụ, biên dịch thành một tệp libbridge_compare.so. Không triển khai lại thuật toán riêng cho JNI và FFM.
2. **Một ABI:** cùng chữ ký C, quy ước gọi, kích thước kiểu, thứ tự tham số, alignment, symbol name và ownership của các pointer.
3. **Một tập đầu vào:** mảng rỗng; mảng một phần tử; số âm; số lớn ở biên 32-bit; độ dài tối đa hợp lệ; độ dài không hợp lệ.
4. **Một hợp đồng đầu ra:** kiểm tra kết quả số nguyên 64-bit và mã trạng thái lỗi; ánh xạ lỗi về cùng loại Java exception ở lớp adapter.
5. **Một oracle độc lập:** Java tự tính expected value. Nếu chỉ so JNI == FFM, hai đường có thể cùng bị lỗi tràn số hoặc đọc sai offset mà vẫn “PASS”.
6. **Một môi trường có thể tái lập:** ghi JDK, OS, kiến trúc, compiler, cờ build, đường dẫn file native, version/hash và JVM native access flags.

Tính **đúng đắn** và **hiệu năng** phải đánh giá riêng. Một phép thử parity không đủ để tuyên bố JNI hay FFM nhanh hơn.

## 2. Hợp đồng C chung: dữ liệu, kết quả, lỗi

Chọn phép tính tổng có trọng số của mảng số nguyên 32-bit:

\[
\mathrm{weightedSum}(a)=\sum_{i=0}^{n-1}(i+1)\cdot a[i].
\]

Chữ ký ABI C:

~~~c
#include <stdint.h>

int32_t weighted_sum_i32(
    const int32_t *values,
    int32_t count,
    int64_t *result_out
);
~~~

Hợp đồng:

- **values** trỏ tới ít nhất count phần tử int32_t còn sống trong suốt lời gọi; nếu count bằng 0 thì được truyền NULL.
- **count** hợp lệ từ 0 đến 1024; số âm, vượt 1024 hoặc pointer không hợp lệ theo điều kiện đầu vào bị từ chối.
- **result_out** bắt buộc trỏ tới vùng 8 byte hợp lệ để ghi kết quả int64_t; không được NULL.
- **Giá trị return của C** là mã trạng thái int32_t: 0 khi thành công, -1 khi tham số không hợp lệ. Tổng được ghi vào *result_out, không dùng giá trị return làm tổng.
- Hàm **không lưu giữ pointer**, không sửa input, không cấp phát bộ nhớ còn sống sau khi return, không gọi callback và không dùng state global.
- Với count ≤ 1024, kể cả tất cả phần tử có trị tuyệt đối cực đại của số có dấu 32-bit, tổng trọng số vẫn nằm trong phạm vi int64_t. Chọn giới hạn này để ví dụ không phụ thuộc vào signed overflow của C (undefined behavior).
- Demo dùng ABI Linux x86-64, trong đó int32_t là kiểu số nguyên 32-bit, int64_t là số 64-bit và con trỏ phù hợp ABI C mà FFM linker hỗ trợ. Chuyển OS/CPU/compiler cần kiểm tra lại calling convention, symbol export và layout.

Việc trả **status tách khỏi kết quả** rất quan trọng: nếu trả -1 làm sentinel lỗi thì một kết quả hợp lệ bằng -1 sẽ trở nên mơ hồ.

## 3. Một tệp C triển khai hàm nghiệp vụ và JNI adapter

Tạo tệp **bridge_compare.c**:

~~~c
#include <stdint.h>
#include "CompareJniFfm.h"

enum { MAX_COUNT = 1024 };

// Hàm nghiệp vụ duy nhất, được cả JNI lẫn FFM gọi.
int32_t weighted_sum_i32(
        const int32_t *values,
        int32_t count,
        int64_t *result_out) {

    if (result_out == NULL ||
            count < 0 ||
            count > MAX_COUNT ||
            (count > 0 && values == NULL)) {
        return -1;
    }

    int64_t sum = 0;
    for (int32_t i = 0; i < count; i++) {
        sum += (int64_t) values[i] * (int64_t) (i + 1);
    }
    *result_out = sum;
    return 0;
}

static void throw_invalid(JNIEnv *env) {
    jclass exception_class = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (exception_class != NULL) {
        (*env)->ThrowNew(
                env, exception_class, "native rejected input");
    }
}

// JNI adapter chuyển int[] thành con trỏ rồi gọi hàm nghiệp vụ trên.
JNIEXPORT jlong JNICALL
Java_CompareJniFfm_jniSum(
        JNIEnv *env, jclass klass, jintArray input) {
    (void) klass;

    if (input == NULL) {
        throw_invalid(env);
        return 0;
    }

    jsize count = (*env)->GetArrayLength(env, input);
    jint *elements = NULL;

    if (count > 0) {
        elements = (*env)->GetIntArrayElements(env, input, NULL);
        if (elements == NULL) {
            // JNI không cấp được mảng; JVM báo lỗi tương ứng.
            return 0;
        }
    }

    int64_t answer = 0;
    int32_t status = weighted_sum_i32(
            (const int32_t *) elements,
            (int32_t) count,
            &answer);

    if (elements != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, input, elements, JNI_ABORT);
    }

    if (status != 0) {
        throw_invalid(env);
        return 0;
    }

    return (jlong) answer;
}
~~~

**Những chi tiết cần đọc chính xác:**

- Header CompareJniFfm.h **được sinh bằng javac -h** từ phương thức native của lớp Java ở phần sau. Không tự đoán tên symbol JNI khi package hoặc tên phương thức thay đổi.
- JNI GetIntArrayElements có thể **pin hoặc copy** mảng Java tùy JVM. Không được giả định địa chỉ trả về luôn là địa chỉ trực tiếp bên trong Java heap.
- JNI_ABORT nói rằng wrapper chỉ **đọc** dữ liệu; không yêu cầu chép thay đổi từ native buffer về mảng Java. Thao tác Release bắt buộc được thực hiện sau mỗi lần GetIntArrayElements thành công, kể cả khi C trả lỗi.
- Trường hợp input rỗng dùng NULL/count=0 đúng như hợp đồng C; hàm C không dereference NULL.
- Nếu GetIntArrayElements không cấp được buffer, JNI thông thường thiết lập exception đang chờ; trả 0 tại đây chỉ là giá trị theo chữ ký JNI khi có exception, **không phải** giá trị nghiệp vụ hợp lệ.
- JNI adapter **không tự tính tổng**, mà gọi trực tiếp hàm weighted_sum_i32. FFM sẽ gọi đúng hàm này, tránh có hai bản thuật toán C.
- Hàm nghiệp vụ không giữ tham chiếu sau khi return. Nếu API thực tế giữ con trỏ hoặc xử lý bất đồng bộ, không được áp dụng vòng đời buffer ngắn như ví dụ.

GCC trên Linux với visibility mặc định xuất symbol C global weighted_sum_i32. Khi dự án bật hidden visibility, phải công khai symbol bằng export annotation phù hợp. Nếu mã native được biên dịch bằng C++, dùng extern "C" cho C ABI để tránh name mangling.

## 4. Chương trình Java gọi cả hai đường

Tạo tệp **CompareJniFfm.java** trong **default package**. Cả hai đường sử dụng cùng thư viện do System.load nạp. Chương trình có thể biên dịch trên **JDK 22+**; ví dụ kiểm thử tập trung vào Linux x86-64.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Objects;

public final class CompareJniFfm {
    private static final int MAX_COUNT = 1024;

    static {
        System.load(Path.of("libbridge_compare.so")
                .toAbsolutePath().toString());
    }

    private static native long jniSum(int[] input);

    // Tìm symbol trong đúng thư viện được System.load nạp
    // qua class loader của lớp này.
    private static final MethodHandle C_SUM = bindCFunction();

    private static MethodHandle bindCFunction() {
        MemorySegment address = SymbolLookup.loaderLookup()
                .find("weighted_sum_i32")
                .orElseThrow(() -> new UnsatisfiedLinkError(
                        "C symbol weighted_sum_i32 is missing"));

        return Linker.nativeLinker().downcallHandle(
                address,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, // return int32_t status
                        ValueLayout.ADDRESS,  // const int32_t *values
                        ValueLayout.JAVA_INT, // int32_t count
                        ValueLayout.ADDRESS   // int64_t *result_out
                ));
    }

    private static long viaJni(int[] input) {
        Objects.requireNonNull(input, "input");
        return jniSum(input);
    }

    private static long viaFfm(int[] input) throws Throwable {
        Objects.requireNonNull(input, "input");

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cValues = input.length == 0
                    ? MemorySegment.NULL
                    : arena.allocateFrom(ValueLayout.JAVA_INT, input);
            MemorySegment cResult =
                    arena.allocate(ValueLayout.JAVA_LONG);

            int status = (int) C_SUM.invokeExact(
                    cValues, input.length, cResult);

            if (status != 0) {
                throw new IllegalArgumentException(
                        "native rejected input");
            }

            return cResult.get(ValueLayout.JAVA_LONG, 0);
        }
    }

    // Phép tính tham chiếu Java, độc lập cả JNI lẫn FFM.
    private static long javaOracle(int[] input) {
        if (input.length > MAX_COUNT) {
            throw new IllegalArgumentException("too many elements");
        }

        long result = 0;
        for (int i = 0; i < input.length; i++) {
            result += (long) input[i] * (i + 1);
        }
        return result;
    }

    private static long verify(int[] input) throws Throwable {
        long expected = javaOracle(input);
        long jni = viaJni(input);
        long ffm = viaFfm(input);

        if (jni != expected || ffm != expected) {
            throw new AssertionError(
                    "Mismatch: input=" + Arrays.toString(input)
                    + ", expected=" + expected
                    + ", JNI=" + jni + ", FFM=" + ffm);
        }
        return expected;
    }

    private static boolean rejectedByJni(int[] input) {
        try {
            viaJni(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    private static boolean rejectedByFfm(int[] input)
            throws Throwable {
        try {
            viaFfm(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Throwable {
        int[][] samples = {
                {},
                {4},
                {1, 2, 3},
                {-3, 0, 4},
                {Integer.MAX_VALUE, Integer.MIN_VALUE}
        };

        for (int[] input : samples) {
            System.out.println(Arrays.toString(input)
                    + " -> " + verify(input));
        }

        int[] maximum = new int[MAX_COUNT];
        Arrays.fill(maximum, 2);
        System.out.println("1024 elements (all 2) -> "
                + verify(maximum));

        int[] oversized = new int[MAX_COUNT + 1];
        if (!rejectedByJni(oversized)
                || !rejectedByFfm(oversized)) {
            throw new AssertionError(
                    "1025 elements must be rejected by both paths");
        }
        System.out.println(
                "1025 elements -> JNI=REJECTED, FFM=REJECTED");
        System.out.println(
                "PASS: JNI and FFM match the Java oracle");
    }
}
~~~

### Tại sao chắc chắn là cùng thư viện C?

System.load dùng **đường dẫn tuyệt đối tới một file libbridge_compare.so**. Tại thời điểm lớp được khởi tạo, JNI liên kết phương thức jniSum với symbol Java_CompareJniFfm_jniSum của file ấy. Tiếp theo, **SymbolLookup.loaderLookup()** của FFM tra cứu các symbol trong những thư viện đã được System.load/System.loadLibrary nạp qua **class loader đang gọi**; do đó FFM tìm symbol nghiệp vụ weighted_sum_i32 của **cùng file đã load**. Không có lời gọi libraryLookup để nạp một thư viện C khác.

Trong JDK 22, loaderLookup chỉ thấy những library thuộc phạm vi class loader đó, không tự quét mọi native library trong process. Nếu dùng plugin system nhiều class loader, phải kiểm tra đúng phạm vi và lifetime của thư viện được load.

### Giải mã các kiểu trong FunctionDescriptor

| Tham số C | FFM layout | Đối số Java của MethodHandle |
| --- | --- | --- |
| Giá trị trả về int32_t status | JAVA_INT | int |
| const int32_t *values | ADDRESS | MemorySegment |
| int32_t count | JAVA_INT | int |
| int64_t *result_out | ADDRESS | MemorySegment |

Trên ABI mục tiêu, MemorySegment của pointer chứa địa chỉ native; kiểu Java long **không được thay** cho ADDRESS chỉ vì pointer cũng thường dài 8 byte trên nền tảng 64-bit. Cùng ý nghĩa, cResult được cấp phát theo **JAVA_LONG** vì ô nhớ chứa **giá trị int64_t**, không phải pointer.

MethodHandle.invokeExact phải nhận đúng **(MemorySegment, int, MemorySegment)** và trả đúng **int**, tương ứng descriptor; sai kiểu có thể gây WrongMethodTypeException, còn **descriptor sai ABI** có thể dẫn tới memory corruption hoặc crash.

### Vòng đời buffer ở hai đường

- **JNI:** GetIntArrayElements tạo một vùng có thể pin/copy; C dùng đồng bộ và không giữ pointer; ReleaseIntArrayElements với JNI_ABORT diễn ra trước khi Java nhận kết quả.
- **FFM:** arena.allocateFrom(JAVA_INT, input) copy các số nguyên sang native segment, cấp thêm ô int64_t cho output; C dùng trong thời gian arena còn sống; try-with-resources đóng arena sau khi đọc kết quả.
- **Đầu vào rỗng:** FFM truyền MemorySegment.NULL, JNI truyền NULL; C chấp nhận NULL khi count=0.
- **Lỗi:** khi status khác 0, không đọc cResult vì C **không cam kết ghi output trong trường hợp lỗi**. JNI cũng chỉ trả kết quả khi status==0.
- **Null Java array:** cả wrapper viaJni/viaFfm chuẩn hóa bằng Objects.requireNonNull trước khi đi vào native; do đó cả hai có cùng NullPointerException tại biên Java.

FFM có các kiểm tra phạm vi/scope của MemorySegment ở phía Java, nhưng C **không tự động** trở nên an toàn trước pointer sai kích thước, use-after-free hoặc data race.

## 5. Biên dịch và chạy trên Linux x86-64

Chuẩn bị JDK **22 hoặc mới hơn**, GCC và thiết lập JAVA_HOME trỏ tới đúng thư mục JDK. Hai tệp bridge_compare.c và CompareJniFfm.java cùng thư mục làm việc.

~~~bash
# Xác nhận môi trường:
java -version
javac -version
gcc --version

# Biên dịch Java, tạo CompareJniFfm.h cho JNI:
javac -h . CompareJniFfm.java

# Build DUY NHẤT một thư viện dùng cho cả hai đường:
gcc -std=c11 -O2 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  bridge_compare.c -o libbridge_compare.so

# Xác nhận symbol C API lẫn JNI bridge:
nm -D libbridge_compare.so | grep -E \
  'weighted_sum_i32|Java_CompareJniFfm_jniSum'

# Chạy đối chiếu. Classpath code được cho phép native access:
java --enable-native-access=ALL-UNNAMED CompareJniFfm
~~~

Cờ **--enable-native-access=ALL-UNNAMED** cần cho những lời gọi FFM restricted như Linker.downcallHandle trong mã classpath; với ứng dụng modular nên bật theo đúng tên module. Chính sách cảnh báo/hạn chế native access còn thay đổi giữa các đời JDK, không nên phụ thuộc vào việc một bản JDK cũ chỉ in warning.

Không cần --enable-preview trên JDK 22+ cho API java.lang.foreign chuẩn. Trên JDK 17, JNI chạy được nhưng không biên dịch được source FFM này; nếu muốn test JVM đời cũ, cần tách bản JNI-only và vẫn giữ nguyên C library/test vectors.

**Output kỳ vọng** của chương trình:

~~~text
[] -> 0
[4] -> 4
[1, 2, 3] -> 14
[-3, 0, 4] -> 9
[2147483647, -2147483648] -> -2147483649
1024 elements (all 2) -> 1049600
1025 elements -> JNI=REJECTED, FFM=REJECTED
PASS: JNI and FFM match the Java oracle
~~~

Ba phép tính hữu ích để tự kiểm tra:

- [1, 2, 3]: 1×1 + 2×2 + 3×3 = 14.
- [2147483647, -2147483648]: 2147483647 + 2×(-2147483648) = **-2147483649**, cần long/int64_t.
- 1024 phần tử đều bằng 2: 2×(1+2+...+1024) = 1024×1025 = **1049600**.

Program chỉ in **PASS** nếu hai đường đều khớp oracle cho mọi input hợp lệ và cùng từ chối input 1025 phần tử với IllegalArgumentException. Đây là kiểm thử parity của API mẫu; không phải chứng minh mọi native API khác đều tương đương.

### Khắc phục sự cố build thường gặp

- **JNI UnsatisfiedLinkError:** sai tên export Java_CompareJniFfm_jniSum, sai package/class, file .so không nạp được, hoặc bitness không hợp lệ. Sinh header lại bằng javac -h và xem nm -D.
- **FFM báo thiếu weighted_sum_i32:** symbol bị static/hidden hoặc FFM đang tra sai class loader. Kiểm tra nm -D libbridge_compare.so và thứ tự System.load → loaderLookup.
- **FFM WrongMethodTypeException:** kiểu Java tại invokeExact khác kiểu MethodHandle yêu cầu; đối chiếu toàn bộ descriptor, không chỉ giá trị.
- **IllegalCallerException/native-access warning:** thiếu cấu hình native access theo JDK/module.
- **C compile không tìm jni.h:** JAVA_HOME trỏ sai JDK hoặc thiếu include/linux, hoặc nhầm header đã sinh.
- **Trên macOS/Windows:** phần mở rộng .so, GCC flags/JNI headers, export và calling convention khác. Đây là **ví dụ build Linux**; không chạy nguyên các lệnh đó trên hệ điều hành khác.

## 6. Bảng so sánh JNI và FFM theo cùng phép tính

| Khía cạnh | JNI | FFM (JDK 22+) | Điều phải kiểm tra |
| --- | --- | --- | --- |
| Hàm nghiệp vụ | JNI adapter gọi weighted_sum_i32 | MethodHandle gọi thẳng weighted_sum_i32 | Cùng symbol trong cùng .so |
| Binding | Native method + header/symbol Java_... | Linker + SymbolLookup + FunctionDescriptor | Chữ ký trùng ABI |
| Dữ liệu int[] | GetIntArrayElements, có thể pin hoặc copy | Arena.allocateFrom(JAVA_INT, input) copy vào memory | Thứ tự/signedness/độ dài như nhau |
| Truyền độ dài | jsize → int32_t | Java int → JAVA_INT | Không sai offset hoặc count |
| Kết quả | C ghi int64_t; JNI trả jlong | C ghi int64_t; FFM đọc JAVA_LONG | Không truncation 64-bit |
| Lỗi C | JNI ThrowNew | Java kiểm tra status và throw | Cùng loại exception bên ngoài |
| Quản lý buffer | ReleaseIntArrayElements(JNI_ABORT) | Arena đóng sau downcall | Không giữ pointer sau lifetime |
| Native access | Quy định JNI và phiên bản JVM | Restricted linking API | JVM flags đúng module/JDK |
| Callback | C gọi Java thông qua JNI | FFM upcall stub/MethodHandle | Demo chưa có callback |
| Đồng thời | Phụ thuộc hợp đồng C/handle | Phụ thuộc hợp đồng C/handle | Binding không làm C tự thread-safe |
| Đóng gói | C JNI glue + .so/.dll | Descriptor Java + .so/.dll | Kiểm tra native build/distribution |
| Hiệu năng | Phụ thuộc call + copy/pin + release | Phụ thuộc linker + copy + arena | Benchmark riêng sau parity |

Không kết luận FFM luôn nhanh hơn hoặc luôn an toàn hơn JNI. FFM có API khai báo rõ layout và scope; JNI dùng API native lâu đời với khả năng tùy biến sâu. Sự phù hợp phụ thuộc phiên bản JDK, độ phức tạp C ABI, callback/ownership, native build và workload thực tế.

## 7. Mở rộng tập test để bắt lỗi bridge khó thấy

### Ma trận đầu vào

| Trường hợp | Input ví dụ | Expected/kiểm tra |
| --- | --- | --- |
| Không phần tử | [] | 0; NULL + count=0 hợp lệ |
| Một phần tử | [4] | 4 |
| Thứ tự/trọng số | [1, 2, 3] | 14 |
| Có số âm | [-3, 0, 4] | 9 |
| Biên int32 | [MAX_INT, MIN_INT] | -2147483649 kiểu long |
| Biên size hợp lệ | 1024 phần tử đều là 2 | 1049600 |
| Vượt max | 1025 phần tử | C status -1, Java IllegalArgumentException |
| Null Java array | null | Cả hai Java wrapper throw NullPointerException |
| Lặp lại | Cùng dãy nhiều lần | Giá trị không lệ thuộc trạng thái lần trước |
| Đầu vào bị thay đổi ở caller | Đổi một phần tử giữa hai lời gọi | Kết quả mới khớp oracle mới |

Đối với hệ thống thật, bổ sung property-based testing với **PRNG seed cố định**, từ đó có thể tái tạo input gây lỗi. Giữ seed và minimal failing vector trong log. Nếu muốn so chính xác lỗi, trước tiên xác định hợp đồng public API gồm **kiểu exception, error code hay message**; đừng coi khác biệt message nội bộ là thất bại nếu API chỉ cam kết loại lỗi.

### Bất biến dữ liệu và quyền sở hữu

Hàm nghiệp vụ khai báo const int32_t *values, vì vậy **không có quyền sửa input** theo hợp đồng. Tuy nhiên với JNI, JNI_ABORT có thể bỏ các thay đổi xảy ra trên bản sao native; nhìn vào Java array sau call **không đủ** chứng minh C chưa từng sửa native buffer. Khi cần xác minh mạnh, instrument C/test native với buffer riêng và kiểm tra raw memory.

Khi C trả status lỗi, phải coi result_out là **chưa có giá trị được bảo đảm**. Nếu FFM đọc output trước khi kiểm tra status, test có thể thỉnh thoảng sai hoặc vô tình dựa trên memory chưa khởi tạo. Ví dụ đã kiểm tra status trước.

Với native API trả pointer hoặc giữ pointer asynchronous, mở rộng hợp đồng lifetime và data ownership trước khi so JNI/FFM. Đặc biệt, Arena đóng không đồng nghĩa C đã ngừng dùng pointer. JNI Release cũng không bảo đảm C không còn thread riêng đang truy cập vùng đã release.

### Kiểm thử crash/native error trong process cô lập

Không dùng JVM đang phục vụ production để cố ý thử pointer không hợp lệ, địa chỉ giả hoặc use-after-free. Những sai phạm có thể làm sập cả JVM. Hãy dùng executable/test process riêng với AddressSanitizer/LeakSanitizer hoặc Valgrind theo nền tảng khi kiểm thử mã C chủ động vi phạm memory safety.

## 8. Đặt một bộ test contract ở trên cả hai adapter

Trong hệ thống thực, thay vì viết test chỉ gọi JNI rồi chép logic sang test FFM, định nghĩa một interface chung:

~~~java
// Minh họa API hướng kiểm thử, chưa phải chương trình độc lập.
interface NativeWeightedSum {
    long calculate(int[] values);
}
~~~

Để JNI adapter và FFM adapter cài đặt cùng interface. Một bộ parameterized tests chuẩn sẽ:

1. Sinh một input hợp lệ từ tập fixture chung.
2. Tính expected bằng Java oracle trước khi gọi native.
3. Truyền **bản sao cùng nội dung** sang mỗi adapter nếu native API có thể sửa input, hoặc chia sẻ input bất biến khi contract cho phép.
4. So cả hai với expected, kiểm tra lỗi/cạnh biên, xác minh cleanup ở success/exception path.
5. Chạy lại cùng fixtures theo nhiều thread **chỉ khi C API thật cho phép concurrent calls**.

Không dùng output JNI làm expected của FFM: cả hai đường cùng gọi thuật toán C nên cùng có thể mắc một lỗi nghiệp vụ. Oracle độc lập giúp phát hiện trường hợp đó.

Một số dự án dùng Golden Data JSON/CSV. Với bài toán số nguyên này, phải xác định signedness và cách parse integer, không để serialization vô tình biến int64_t thành float hoặc làm mất chính xác các giá trị lớn.

## 9. Kiểm chứng ABI, binary và quy trình phân phối

Java code giống nhau không bảo đảm native artifact được load giống nhau giữa dev và CI. Lưu metadata build kèm .so:

~~~bash
# Chạy trên binary do nhóm kiểm soát và đã xây dựng:
file libbridge_compare.so
nm -D libbridge_compare.so | grep weighted_sum_i32
ldd libbridge_compare.so
sha256sum libbridge_compare.so
~~~

Hãy dùng ldd với native binary đáng tin cậy; không chạy bừa trên file không rõ nguồn. So hash/version và dependency để biết staging/prod không nạp nhầm thư viện cũ. Trong CI/CD nên có:

- Một job build shared C library với header JNI của JDK mục tiêu.
- Một job compile Java/JDK 22+ và chạy bộ vector parity.
- Job thử ABI/OS/architecture chính thức được hỗ trợ, tránh dùng Linux artifact trên Windows/macOS.
- Native unit test để kiểm tra thuật toán C độc lập JNI/FFM.
- Smoke test kiểm tra đúng symbol, đúng đường dẫn load, signed types, lỗi và vòng đời tài nguyên.
- Nếu có JNI-only consumer đời JDK cũ, build/test tách riêng phần đó, vẫn gọi **cùng C API**.
- Khi có compiler flags như -fvisibility=hidden, LTO hoặc C++ ABI, xác minh symbol export vẫn có đúng tên.

Đối với struct hoặc complex C ABI, cần thêm sizeof/alignof, offset và calling convention ở cả phía C và layout FFM. Không mặc định `long` trong C là 64-bit trên mọi OS; ví dụ dùng **int64_t** để đặt kích thước chính xác.

## 10. Performance: đo sau khi đã xác nhận parity

Ví dụ hiện tại **không phải benchmark**. JNI dùng GetIntArrayElements (có thể pin hoặc copy), còn FFM hiện tại **luôn copy** Java int[] vào vùng Arena mới. Nếu chạy nhiều vòng và so thời gian trực tiếp, kết quả bao gồm chi phí copy, allocation, JNI release và Arena close, không chỉ native call overhead.

Một benchmark có giá trị nên định nghĩa rõ:

- **End-to-end latency:** chuẩn bị input, gọi native, lấy output, cleanup; gần với chi phí thực của API công khai.
- **Pure downcall overhead:** chuẩn bị buffer/method handle trước rồi đo lời gọi, nhưng vẫn giữ buffer sống và ràng buộc ownership.
- **Throughput & contention:** đồng thời có phù hợp với C API không; số thread, kích thước buffer, cache effects, native allocator.
- **JIT warm-up:** dùng JMH, nhiều lần chạy độc lập, xử lý kết quả để tránh dead-code elimination, cùng JDK/CPU/OS/compiler.
- **Phạm vi kết luận:** báo giá trị, phương sai/percentile khi phù hợp và cấu hình; không khẳng định JNI/FFM mặc định nhanh hơn từ một thử nghiệm.

Một chương trình đo “FFM vs JNI” nhưng vô tình đo hai cách marshalling khác nhau vẫn hữu ích nếu câu hỏi là **end-to-end behavior**, song không thể từ đó kết luận riêng về cost của binding.

## 11. Khi C API có String, struct, handle hoặc callback

Mẫu int32[] cố tình đơn giản. Đối với native interoperability thật, parity phải xét thêm:

**String và Unicode.** JNI GetStringUTFChars dùng **modified UTF-8**, khác UTF-8 chuẩn trong trường hợp đặc biệt. FFM arena.allocateFrom(String) trên JDK 22 tạo C string UTF-8 kết thúc NUL. Muốn so cùng bytes phải định nghĩa encoding: ASCII, tiếng Việt, supplementary characters, embedded NUL, chiều dài theo byte và release.

**Struct/union.** Kiểm tra offset, alignment, padding, native endianness, kiểu C long/size_t và struct return. FFM MemoryLayout chỉ đúng khi phản ánh chính xác ABI C. JNI adapter cũng có thể sai khi tự memcpy hoặc cast.

**Native handle/pointer.** Ai create, ai close/free, handle có thread affinity không, callback có thể dùng sau close không? JNI `jlong` chứa địa chỉ và FFM MemorySegment đều không giúp C tự giải phóng một đối tượng bị leak. Arena chỉ quản lý vùng thuộc phạm vi của nó, không tự free mọi pointer do C trả về.

**Callback/upcall.** JNI cần JNIEnv của thread hiện tại, attach thread native khi cần và quản lý reference. FFM upcall stub có lifetime gắn với Arena; phải kiểm tra reentrancy, exception, thread và phạm vi sống của callback pointer.

**C varargs và calling convention.** Không tự suy diễn FunctionDescriptor từ số byte hay số tham số. Các hàm có union, struct by value, errno hoặc varargs cần API binding và test ABI riêng.

Vì vậy bài đối chiếu đơn giản xác lập **phương pháp**; mỗi API C thật sẽ có tập test bổ sung theo kiểu dữ liệu và vòng đời cụ thể.

## 12. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| JNI chạy nhưng FFM không tìm thấy weighted_sum_i32 | Symbol hidden/static/mangled hoặc sai class loader | nm -D, linker export, loaderLookup |
| FFM ném WrongMethodTypeException | invokeExact dùng sai kiểu với MethodHandle | Kiểm tra (MemorySegment,int,MemorySegment)int |
| JVM crash trong downcall | FunctionDescriptor sai ABI hoặc C truy cập pointer sai | Đối chiếu C header, sanitizer trên process cô lập |
| JNI ném UnsatisfiedLinkError | Tên Java_... sai hoặc library không tải đúng | javac -h, nm -D, kiểm tra load path |
| FFM cảnh báo hoặc ném IllegalCallerException | Native access chưa bật đúng module | Flag --enable-native-access theo JDK |
| Chỉ sai với MIN_VALUE/MAX_VALUE | Kết quả bị truncate thành int, sai signedness | Oracle long và vector biên |
| Cùng kết quả nhưng vẫn sai | JNI/FFM cùng gọi C bug hoặc cùng nhầm input | Thêm oracle Java và expected value độc lập |
| Leak sau test | JNI thiếu Release hoặc pointer giữ sau Arena.close | Kiểm tra cleanup và native allocation profiler |
| Sai lúc concurrent | C có state global hoặc dùng chung handle không an toàn | Tài liệu thread policy và stress test có kiểm soát |
| Chạy Linux thành công nhưng Windows lỗi | ABI, tên .dll, export, compiler khác | Ma trận build/test theo nền tảng |
| Benchmark cho kết quả bất nhất | Đo copy/allocation/JIT thay vì cùng workload | JMH, warm-up, tách marshalling khỏi call |

## 13. Checklist chốt kết quả đối chiếu

- [ ] Có một header/hợp đồng C làm chuẩn: function name, status, pointer, count, ownership và kích thước kiểu.
- [ ] JNI và FFM cùng load/resolve **một binary** và cùng chạy một C function.
- [ ] Có oracle Java độc lập; cả JNI và FFM được kiểm tra với expected.
- [ ] Có vector rỗng, số âm, thứ tự, 32-bit extremes, 64-bit result, size 1024 và size 1025.
- [ ] Trường hợp lỗi được so theo contract Java; không đọc result_out khi C báo lỗi.
- [ ] JNI Get/Release và FFM Arena scope được quản lý đầy đủ; không để C giữ pointer sau vòng đời.
- [ ] JNI header từ javac -h và FFM descriptor khớp chính xác cùng ABI.
- [ ] Mã Java và JNI/C build thành công trên JDK/OS được chỉ định; symbol/native access được xác nhận.
- [ ] CI lưu compiler/JDK/native library version/hash và kết quả test có thể lặp lại.
- [ ] Benchmark nếu có là bước riêng, nói rõ đang đo API end-to-end hay chi phí downcall.
- [ ] Nếu native API thật có callback/handle/thread affinity, có test riêng cho vòng đời và đồng thời.

**Kết luận:** Hãy cố định **hàm C và tập đầu vào**, coi JNI/FFM là hai cơ chế binding cần kiểm chứng, rồi so **từng kết quả và hành vi lỗi với oracle độc lập**. Khi phép thử parity vượt qua các trường hợp biên, mới tiếp tục đánh giá mức độ dễ bảo trì, hỗ trợ JDK và hiệu năng để chọn JNI hay FFM.

### Tài liệu kỹ thuật

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chuẩn từ JDK 22.
- [JDK 22 SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): loaderLookup cho thư viện đã load qua JNI.
- [JDK 22 SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): cấp phát từ int[] và String.
- [Oracle JDK 22 FFM Guide](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FunctionDescriptor, Linker, Arena và native access.
- [JNI Specification](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/index.html): symbol names, JNI arrays, exceptions và reference lifetime.
