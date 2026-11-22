# Trạng thái toàn cục, biến cục bộ theo luồng và tính tái nhập của hàm C khi gọi từ Java

## 1. Vì sao đây là vấn đề của Java Native Interoperability?

Khi Java gọi mã C qua JNI (Java Native Interface) hoặc Foreign Function & Memory API (FFM), lời gọi có thể đi vào thư viện native được nhiều luồng sử dụng đồng thời. JVM quản lý luồng và đối tượng Java, nhưng **không tự biến những biến toàn cục, bộ đệm tĩnh hay hàm C thành an toàn luồng**.

Ba câu hỏi cần tách biệt:

1. **Trạng thái đặt ở đâu?** Một giá trị dùng chung cho thư viện/tiến trình, một giá trị riêng cho mỗi luồng hệ điều hành, hay một giá trị mới cho từng lần gọi?
2. **Điều gì xảy ra khi nhiều luồng cùng truy cập?** Có data race, mất cập nhật, đọc trạng thái không nhất quán hoặc vi phạm quy tắc vòng đời bộ nhớ hay không?
3. **Điều gì xảy ra khi chính hàm ấy được gọi lồng nhau trước khi lần gọi trước hoàn tất?** Đây là câu hỏi về *tính tái nhập* (*reentrancy*), khác với an toàn luồng.

Ví dụ về một chuỗi gọi lồng nhau:

```text
Java thread T
  -> JNI hàm C f()
       -> f() gọi callback Java
            -> callback lại gọi JNI hàm C f()
                 -> f() lần 2 chạy khi f() lần 1 chưa kết thúc
```

Trường hợp này có thể xảy ra **trên cùng một luồng**, ngay cả khi chương trình không tạo luồng thứ hai.

## 2. Ba nơi lưu trạng thái trong C

### 2.1. Biến toàn cục và biến `static`: trạng thái chia sẻ

```c
/* Minh họa một phần C, không phải chương trình độc lập. */
static int request_count = 0;

int next_count(void) {
    return ++request_count;
}
```

`request_count` có *static storage duration*: được khởi tạo một lần và tồn tại trong suốt thời gian thực thể thư viện/chương trình chứa nó còn được tải. `static` ở phạm vi tệp giới hạn liên kết tên (*internal linkage*), **không tạo bản sao cho từng luồng**. Một biến toàn cục không có `static` vẫn là trạng thái chia sẻ, chỉ khác khả năng liên kết/hiển thị tên theo quy tắc C và công cụ liên kết.

Hai luồng C đồng thời thực hiện `++request_count` mà thiếu đồng bộ sẽ truy cập xung đột một đối tượng không nguyên tử. Theo mô hình bộ nhớ C, đó là **data race dẫn đến hành vi không xác định (undefined behavior)**; không thể chỉ dự đoán là “thỉnh thoảng mất một lần tăng”. `volatile` trong C không sửa được data race.

Đổi sang nguyên tử khi chỉ cần một bộ đếm độc lập:

```c
#include <stdatomic.h>

static atomic_int request_count = ATOMIC_VAR_INIT(0);

int next_count(void) {
    return atomic_fetch_add_explicit(
        &request_count, 1, memory_order_relaxed
    ) + 1;
}
```

`memory_order_relaxed` đủ để mỗi phép tăng bộ đếm là nguyên tử và không bị mất cập nhật; nó **không** tạo quan hệ công bố/quan sát dữ liệu khác. Nếu trạng thái bao gồm nhiều trường phải nhất quán cùng nhau, cần thiết kế thêm cơ chế đồng bộ phù hợp, chẳng hạn mutex hoặc giao thức nguyên tử với thứ tự bộ nhớ đúng. Bản thân biến `static const` chỉ an toàn khi dữ liệu thực sự bất biến và được khởi tạo/công bố đúng cách.

**Phạm vi chia sẻ:** cách tải thư viện native, bản sao thư viện và class loader có thể ảnh hưởng việc cùng dùng một thực thể native. Không giả định mỗi đối tượng Java sẽ tự có một bản sao biến `static` C.

### 2.2. Biến cục bộ tự động: thông thường riêng cho từng lần gọi

```c
int sum_1_to_n(int n) {
    int sum = 0;                 /* Mỗi lần gọi có biến sum riêng. */
    for (int i = 1; i <= n; ++i) {
        sum += i;
    }
    return sum;
}
```

Ở đây `sum` là biến tự động của từng lần gọi, kể cả khi hàm được gọi lồng hoặc đệ quy. Tuy nhiên, đây chỉ là ví dụ cho đầu vào nhỏ để tránh tràn `int`: **biến cục bộ không tự làm cả hàm an toàn** nếu hàm còn truy cập đối tượng chia sẻ qua con trỏ, gọi API không an toàn hoặc trả về con trỏ trỏ vào bộ nhớ đã hết vòng đời.

Một tham số con trỏ có thể dẫn tới vùng nhớ chung dù chính tham số đó nằm trên stack của từng lời gọi.

### 2.3. Thread-local storage (TLS): riêng cho từng luồng hệ điều hành

C11 có `_Thread_local`:

```c
static _Thread_local int calls_on_this_thread = 0;

int next_on_thread(void) {
    return ++calls_on_this_thread;
}
```

Mỗi **OS thread** nhận một đối tượng `calls_on_this_thread` riêng, khởi tạo ban đầu bằng `0`. Các lần gọi trên cùng luồng sử dụng lại đối tượng ấy; kết thúc một hàm không xóa TLS.

Có thể gặp các cơ chế tương đương hoặc gần tương đương theo nền tảng: `thread_local` trong C++11, `pthread_key_create`/`pthread_getspecific` trên POSIX, TLS/FLS trên Windows. Cơ chế khởi tạo, hủy, destructor và khả năng hỗ trợ của compiler khác nhau; không coi chúng là hoán đổi hoàn toàn ở cấp mã nguồn.

TLS giải quyết việc **các OS thread giẫm lên cùng một biến**, nhưng không tạo trạng thái mới cho từng lời gọi, yêu cầu HTTP hoặc tác vụ trong thread pool. Ví dụ, tác vụ A và B chạy lần lượt trên cùng worker thread sẽ cùng nhìn thấy TLS của worker đó. Với Java virtual thread, cũng không được coi TLS C là trạng thái riêng của virtual thread: TLS native gắn với luồng hệ điều hành thực sự thực thi mã C.

## 3. Thread-safe và reentrant khác nhau thế nào?

- **Thread-safe (an toàn luồng):** nhiều luồng gọi đồng thời vẫn thỏa mãn hợp đồng của hàm, với điều kiện đầu vào/vòng đời bộ nhớ hợp lệ.
- **Reentrant (tái nhập):** một lời gọi mới có thể bắt đầu trước khi lời gọi cũ của cùng hàm hoàn thành, kể cả trên **cùng luồng**, mà không phá hỏng trạng thái hoặc mắc kẹt.
- **Recursion (đệ quy):** một dạng tái gọi theo đồ thị lời gọi; một hàm có thể không tự đệ quy nhưng vẫn bị tái nhập thông qua callback, signal handler hoặc đường gọi khác. *Reentrant* thông thường **không đồng nghĩa** với *async-signal-safe*: các signal handler còn có quy tắc chặt hơn.

| Cách triển khai | Gọi đồng thời giữa nhiều luồng | Gọi lồng trên cùng luồng |
| --- | --- | --- |
| `static int` thay đổi không đồng bộ | Có data race, không an toàn | Có thể ghi đè trạng thái |
| Biến chung được khóa bằng mutex thường | Có thể an toàn nếu mọi truy cập cùng tuân thủ khóa | Có thể deadlock nếu giữ khóa rồi tái nhập |
| Biến `_Thread_local` | Tách đối tượng giữa các OS thread | Vẫn dùng chung một đối tượng khi tái nhập trên cùng OS thread |
| Dữ liệu thuần cục bộ theo lần gọi | Thường an toàn nếu các phụ thuộc cũng an toàn | Thường tái nhập nếu không phụ thuộc trạng thái chia sẻ |
| Phép toán nguyên tử trên một biến | An toàn đối với thao tác được nguyên tử hóa | Tính tái nhập của *toàn hàm* vẫn phụ thuộc các bước khác |

**Phản ví dụ với TLS:** một hàm trả con trỏ đến bộ đệm TLS vẫn có thể làm hỏng kết quả của lần gọi đang chạy:

```c
/* Đoạn minh họa C; cần #include <stdio.h>. */
static _Thread_local char scratch[32];

const char *number_text(int n) {
    snprintf(scratch, sizeof scratch, "%d", n);
    return scratch;
}

/* Cùng OS thread: */
const char *first = number_text(10);
const char *second = number_text(20);
printf("%s | %s\n", first, second);  /* 20 | 20 */
```

`first` và `second` cùng trỏ đến một bộ đệm. Nếu callback tái nhập `number_text()` trong khi người gọi đầu tiên còn cần nội dung cũ, nội dung bị ghi đè. TLS ngăn *luồng khác* ghi vào cùng bộ đệm, nhưng không ngăn *lần gọi sau trên cùng luồng* ghi đè.

Cách thiết kế tốt hơn là để mỗi lần gọi có bộ đệm riêng do người gọi sở hữu:

```c
#include <stdio.h>
#include <stddef.h>

/* Trả -1 nếu không ghi đủ; không giữ con trỏ dst sau khi trả về. */
int number_text_into(char *dst, size_t capacity, int n) {
    if (dst == NULL || capacity == 0) {
        return -1;
    }
    int required = snprintf(dst, capacity, "%d", n);
    if (required < 0 || (size_t)required >= capacity) {
        return -1;
    }
    return 0;
}
```

Hàm này không giữ trạng thái trong bộ đệm chung. Người gọi phải cung cấp các bộ đệm đủ lớn, còn sống và không bị truy cập ghi đồng thời trái phép. Nếu hai lời gọi cùng truyền một `dst`, tính an toàn lại phụ thuộc người gọi.

## 4. Ví dụ thực hành Java 17 + JNI + C11

Ví dụ dưới đây cố ý minh họa cả ba dạng: **một bộ đếm toàn cục nguyên tử**, **một bộ đếm TLS theo OS thread**, và **một hàm tính toán dùng biến theo lần gọi**. Tất cả mã trong phần này có thể chạy trên Linux với JDK 17+ và compiler C hỗ trợ C11.

### 4.1. Tệp `NativeState.java`

```java
public final class NativeState {
    static {
        System.loadLibrary("native_state");
    }

    private static native int nextGlobal();
    private static native int nextOnThread();
    private static native int sum1ToN(int n);

    public static void main(String[] args) throws InterruptedException {
        System.out.println("global 1 = " + nextGlobal());
        System.out.println("global 2 = " + nextGlobal());

        System.out.println("main TLS 1 = " + nextOnThread());
        System.out.println("main TLS 2 = " + nextOnThread());

        Thread worker = new Thread(() -> {
            System.out.println("worker TLS 1 = " + nextOnThread());
            System.out.println("worker TLS 2 = " + nextOnThread());
        }, "demo-worker");

        worker.start();
        worker.join();

        System.out.println("main TLS 3 = " + nextOnThread());
        System.out.println("sum1ToN(5) = " + sum1ToN(5));
    }
}
```

`NativeState` đặt trong default package để đơn giản hóa ví dụ. Trong dự án có package, hãy dùng tên package thực và **để `javac -h` tạo header JNI** thay vì tự đoán tên symbol đã mã hóa.

### 4.2. Tệp `native_state.c`

```c
#include "NativeState.h"
#include <stdatomic.h>

/* Một đối tượng chia sẻ trong thực thể thư viện này. */
static atomic_int global_hits = ATOMIC_VAR_INIT(0);

/* Một đối tượng riêng cho mỗi OS thread. */
static _Thread_local int tls_hits = 0;

JNIEXPORT jint JNICALL
Java_NativeState_nextGlobal(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;

    return (jint)(atomic_fetch_add_explicit(
        &global_hits, 1, memory_order_relaxed
    ) + 1);
}

JNIEXPORT jint JNICALL
Java_NativeState_nextOnThread(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;

    return (jint)(++tls_hits);
}

JNIEXPORT jint JNICALL
Java_NativeState_sum1ToN(JNIEnv *env, jclass cls, jint n) {
    (void)cls;

    /* Giới hạn đầu vào để tổng không tràn jint (ít nhất 32 bit). */
    if (n < 0 || n > 1000) {
        jclass error_class = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException"
        );
        if (error_class != NULL) {
            (*env)->ThrowNew(
                env, error_class, "n must be between 0 and 1000"
            );
        }
        return 0;  /* Java nhìn thấy exception đang chờ nếu ThrowNew thành công. */
    }

    jint sum = 0;
    for (jint i = 1; i <= n; ++i) {
        sum += i;
    }
    return sum;
}
```

Từng giá trị có ý nghĩa:

- `global_hits` được mọi OS thread đi qua cùng thực thể thư viện nhìn thấy; `atomic_fetch_add_explicit` làm từng lần tăng nguyên tử.
- `tls_hits` tăng từ `1` trên mỗi OS thread mới; nó **không reset sau mỗi JNI call**.
- `sum` chỉ thuộc lần gọi `sum1ToN` hiện tại. Giới hạn `n <= 1000` làm tổng tối đa `500500`, không vượt phạm vi `jint` thông dụng được JNI định nghĩa là số nguyên có dấu 32 bit.
- Mẫu JNI nhận `JNIEnv *` và `jclass` vì các phương thức Java là `static`; `JNIEnv *` thuộc luồng đang gọi và không được lưu rồi dùng trên luồng khác.

### 4.3. Biên dịch và chạy (Linux)

Đặt hai tệp trong cùng thư mục, cấu hình `JAVA_HOME` trỏ tới **JDK** (chứa thư mục `include`), rồi chạy:

```bash
javac -h . NativeState.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnative_state.so native_state.c

java -Djava.library.path=. NativeState
```

Nếu dùng compiler có tên `gcc`, có thể thay `cc` bằng `gcc`. Trên macOS cần header dưới `include/darwin` và tùy chọn tạo dynamic library phù hợp; trên Windows dùng định dạng/thư viện/lệnh compiler tương ứng. Tên thư viện phải tương thích quy tắc `System.loadLibrary` của nền tảng.

**Stdout chính xác** trong một lần chạy độc lập của chương trình:

```text
global 1 = 1
global 2 = 2
main TLS 1 = 1
main TLS 2 = 2
worker TLS 1 = 1
worker TLS 2 = 2
main TLS 3 = 3
sum1ToN(5) = 15
```

Thứ tự được xác định: Java in hai giá trị global và hai giá trị TLS của main trước `worker.start()`; `worker.join()` đợi worker in xong rồi mới in TLS lần ba của main. Đây là ví dụ Java 17 với platform thread thông thường. Nếu một thành phần khác gọi vào chính các biến native trong lúc chạy, không thể giả định global bắt đầu và tăng chỉ theo trình tự trên.

## 5. Vì sao chỉ khóa bên Java thường chưa đủ?

Giả sử Java bọc một native method bằng `synchronized`:

```java
private static native int updateNativeGlobal();

public static synchronized int guardedUpdate() {
    return updateNativeGlobal();
}
```

Cách này chỉ tuần tự hóa **những bên gọi có cùng khóa Java và thực sự đi qua `guardedUpdate()`**. Nó không bảo vệ dữ liệu C nếu:

- native worker thread cập nhật cùng dữ liệu mà không lấy monitor ấy;
- một JNI method khác hoặc thư viện khác truy cập trực tiếp cùng trạng thái;
- C gọi callback và callback tái nhập khi một khóa native không cho phép tái nhập đang được giữ.

Ví dụ, mutex C thông thường bảo vệ một cấu trúc chung có thể khiến hai luồng dùng được một cách an toàn, nhưng nếu C vẫn giữ mutex khi gọi Java callback, callback lại gọi C để lấy **cùng mutex không đệ quy**, luồng có thể tự deadlock. `synchronized` Java là reentrant đối với cùng Java thread, nhưng đặc tính ấy **không tự truyền sang mutex C**.

Thiết kế rõ ràng hơn: sở hữu khóa ở một tầng với quy ước nhất quán; cập nhật cấu trúc chung trong đoạn ngắn; thả khóa trước khi gọi callback có thể tái nhập; không đưa ra con trỏ tới dữ liệu chung đã hết vòng đời bảo vệ.

## 6. Khi thực sự cần trạng thái: truyền context thay vì dùng global

Một giải pháp dễ cô lập hơn là cấp một cấu trúc riêng cho từng thực thể hoặc phiên xử lý:

```c
/* Ví dụ C về API có context; không phải chương trình hoàn chỉnh. */
typedef struct Counter {
    unsigned int value;
} Counter;

unsigned int counter_next(Counter *ctx) {
    return ++ctx->value;
}
```

Hai đối tượng `Counter` tách biệt không giẫm lên dữ liệu của nhau. Nhưng **chia sẻ cùng một con trỏ `ctx` giữa nhiều luồng** vẫn cần đồng bộ; `Counter` không tự thread-safe. Cần quy định rõ:

- ai tạo và giải phóng `Counter`, khi nào được giải phóng;
- con trỏ có được giữ qua lần JNI call hay không; nếu dùng `jlong` làm handle thì phải kiểm tra vòng đời, type và tính hợp lệ, không coi handle tùy ý là con trỏ an toàn;
- callback có được truy cập lại cùng context khi lần gọi trước đang thực hiện hay không;
- bộ nhớ có thể bị Java/native thread khác sửa cùng lúc hay không.

Khi không cần trạng thái, thiết kế nhận đầu vào và trả kết quả bằng bộ nhớ theo lời gọi là cách đơn giản hơn:

```c
#include <stddef.h>

/* data phải trỏ đến ít nhất length byte hợp lệ khi length > 0. */
size_t count_byte(const unsigned char *data,
                  size_t length,
                  unsigned char target) {
    size_t count = 0;
    for (size_t i = 0; i < length; ++i) {
        if (data[i] == target) {
            ++count;
        }
    }
    return count;
}
```

Hàm không giữ trạng thái mutable giữa các lần gọi và có thể tái nhập khi vùng `data` hợp lệ, không bị sửa đồng thời. Từ khóa `const` chỉ ngăn hàm sửa qua tham số này; nó không ngăn một bên khác sửa cùng bộ nhớ.

## 7. Quy tắc JNI/FFM thường bị bỏ sót

### 7.1. `JNIEnv *` và native thread

`JNIEnv *` là giao diện JNI **gắn với thread**; chỉ dùng trên luồng đã nhận nó. Không cất `JNIEnv *` trong biến toàn cục hoặc TLS rồi sử dụng từ một thread khác. Một native thread do C tạo muốn gọi JVM phải có `JavaVM *` phù hợp và attach thread qua `AttachCurrentThread` trước khi dùng JNI; thread đó cần detach thích hợp trước khi kết thúc. `JavaVM *` có thể được lưu để lấy giao diện/attach, còn `JNIEnv *` không thể tùy tiện chia sẻ.

JNI local reference thường chỉ có hiệu lực trong phạm vi native call/local reference frame và theo thread; muốn giữ object Java sau khi lời gọi kết thúc phải dùng global reference và giải phóng đúng bằng `DeleteGlobalRef`. Global reference **không tự đồng bộ dữ liệu bên trong object**. Nếu native code đang chờ khóa và gọi callback Java, cần xét cả thứ tự khóa JVM/native.

### 7.2. Java `ThreadLocal` không đồng nhất với TLS C

`ThreadLocal<T>` lưu trạng thái theo Java `Thread`; C11 `_Thread_local` lưu theo **OS thread**. Trong chương trình dùng platform thread thông thường chúng có thể tương ứng trong thời gian luồng chạy, nhưng đó không phải hợp đồng dữ liệu dùng chung giữa hai hệ thống. Với thread pool, cả Java `ThreadLocal` lẫn TLS native có thể tồn tại giữa các tác vụ trên worker; với virtual thread, không được dùng TLS C để xác định danh tính logic của virtual thread hay request.

Trạng thái gắn với một tác vụ nên được **truyền rõ bằng tham số/context**, hoặc dùng cơ chế do tầng thực thi quản lý, thay vì dựa vào “thread nào đang chạy” ở biên Java/C.

### 7.3. Dữ liệu và bộ nhớ băng qua biên Java/C

Một `jbyteArray`, `ByteBuffer` hay vùng nhớ FFM có thể được nhiều đường gọi truy cập. Việc C dùng biến cục bộ không loại bỏ race trên **vùng nhớ mà con trỏ tham chiếu đến**. Với JNI, tuân thủ đúng hợp đồng của `Get/Release<PrimitiveType>ArrayElements`, `GetPrimitiveArrayCritical` và vòng đời reference. Đặc biệt, không thực hiện thao tác JNI tùy ý hoặc chặn lâu khi đang giữ vùng “critical” theo ràng buộc của JNI.

Với FFM (API chuẩn ổn định từ JDK 22), quản lý lifetime và quyền truy cập của `MemorySegment`/`Arena` là vấn đề bổ sung; **bản thân các quy tắc global/TLS/reentrancy của C vẫn giữ nguyên**. Đừng dùng cú pháp FFM phiên bản 22 như mã chạy được nguyên trạng trên Java 17: trên Java 17 FFM có API incubator khác. Vì thế ví dụ thực hành phía trên dùng JNI để phù hợp Java 17+.

### 7.4. Nguyên tử C không tự mang theo quy tắc đồng bộ Java

C `_Atomic` bảo vệ các thao tác nguyên tử theo mô hình bộ nhớ C. Java `volatile`, `synchronized`, `VarHandle` tuân theo mô hình bộ nhớ Java. Khi cả hai phía cùng thao tác một vùng native hoặc trạng thái liên kết, không suy diễn quan hệ *happens-before* chỉ từ việc “Java đã synchronized” hoặc “C đã dùng relaxed atomic”. Cần hợp đồng truy cập và đồng bộ nhất quán với API, ABI, nền tảng và vòng đời vùng nhớ cụ thể.

## 8. Các lỗi điển hình và cách sửa

| Dấu hiệu | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| Bộ đếm native thỉnh thoảng sai hoặc lỗi khó lặp | `static` C bị nhiều luồng truy cập không đồng bộ; data race/UB | Dùng atomic cho counter độc lập, mutex cho bất biến nhiều trường, hoặc tách state |
| Hai kết quả chuỗi cùng thay đổi | Hàm trả con trỏ tới `static`/TLS scratch buffer | Caller cung cấp buffer; trả bản sao có ownership rõ ràng |
| Kết quả của request B chứa dữ liệu request A | TLS được tái sử dụng bởi cùng worker thread | Reset có chủ đích hoặc truyền context theo request |
| Ứng dụng treo khi native callback gọi lại chính nó | Giữ mutex không đệ quy trong lời gọi có thể tái nhập | Thiết kế lại thứ tự khóa, thả khóa trước callback, tách state theo invocation |
| Crash khi native worker gọi JNI | Dùng sai `JNIEnv *` hoặc reference hết hiệu lực/không đúng thread | Attach thread, lấy `JNIEnv *` riêng, dùng global refs khi cần |
| Đã khóa Java nhưng native vẫn race | Một số đường truy cập C không tuân thủ cùng khóa | Đặt đồng bộ tại nơi thực sự sở hữu trạng thái native |
| Đã dùng TLS nhưng hàm vẫn không tái nhập | Hai lần gọi lồng trên cùng OS thread ghi cùng TLS | Loại bỏ scratch state theo thread khỏi lời gọi tái nhập |
| Mã chạy ở JDK này nhưng lỗi trên JDK khác | Nhầm JNI với FFM phiên bản incubator/preview/standard | Chọn API theo phiên bản JDK; cô lập binding và kiểm tra ABI |

## 9. Checklist khi thiết kế hoặc review một native function

1. **Liệt kê mọi trạng thái** mà hàm đọc/ghi: global, file-scope `static`, local `static`, TLS, heap qua con trỏ, resource của thư viện bên thứ ba, `errno` và dữ liệu callback. Không mặc định `errno` là một biến toàn cục đơn lẻ: các C runtime hiện đại thường cung cấp trạng thái lỗi theo luồng, nhưng cần theo hợp đồng nền tảng cụ thể.
2. **Xác định scope của state:** chia sẻ giữa lời gọi nào, OS thread nào, đối tượng/context nào và phiên xử lý nào? Xác định thời điểm khởi tạo, reset, giải phóng.
3. **Đặt câu hỏi concurrency:** hai thread có thể chạm cùng đối tượng không? Có xảy ra data race C, đọc/ghi ngoài vòng đời, truy cập chéo Java/native không?
4. **Đặt câu hỏi reentrancy:** hàm có thể gọi callback Java, gọi API kích hoạt lại cùng hàm, hoặc giữ mutex/buffer xuyên qua callback không? Có dữ liệu tạm bị ghi đè khi tái nhập không?
5. **Chọn chiến lược nhỏ nhất đủ đúng:** đầu vào/đầu ra theo invocation nếu stateless; context riêng khi state thuộc đối tượng; TLS chỉ khi state thực sự thuộc OS thread; mutex/atomic khi bắt buộc chia sẻ.
6. **Kiểm tra biên JNI/FFM:** `JNIEnv *` đúng thread, references và native memory còn sống, method/symbol JNI đúng, exception được xử lý, buffer không bị giữ quá vòng đời.
7. **Thử dưới tải thực tế:** nhiều platform thread cùng gọi; nhiều tác vụ lần lượt trên thread pool; callback gọi lồng; đầu vào lỗi; shutdown/unload và cleanup. Kiểm tra tính đúng bằng kết quả/bất biến cụ thể, không chỉ thấy chương trình “chạy được”.

**Quy tắc thực hành:** biến global là state chia sẻ; TLS là state theo OS thread; biến automatic là state theo lần gọi. An toàn luồng giải quyết concurrency, còn tái nhập giải quyết lời gọi lồng. Muốn một native function dễ dùng từ Java, hãy làm rõ **ownership, lifetime, synchronization và khả năng callback tái nhập** ngay trong hợp đồng API.