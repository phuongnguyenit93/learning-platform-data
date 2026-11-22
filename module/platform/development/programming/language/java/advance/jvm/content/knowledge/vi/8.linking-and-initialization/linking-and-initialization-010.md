# Khóa khởi tạo lớp, khởi tạo đệ quy và nguy cơ chờ lẫn nhau trong JVM

## 1. Khái niệm: vì sao khởi tạo lớp cần đồng bộ?

Khi chương trình Java lần đầu **chủ động sử dụng** một lớp hoặc giao diện theo những quy tắc của ngôn ngữ/JVM, runtime có thể cần thực hiện **class initialization**: chạy các biểu thức khởi tạo trường `static` và các khối `static { ... }`. Đây là giai đoạn khác với tải lớp (*loading*), xác minh và chuẩn bị (*verification/preparation*) hay giải quyết tham chiếu (*resolution*).

Vì Java cho phép nhiều thread thực thi đồng thời, hai thread có thể cùng muốn sử dụng một lớp **chưa khởi tạo**. JVM phải bảo đảm rằng quá trình khởi tạo được quản lý đúng: một thread đang thực hiện initialization, thread khác không được tự ý chạy lại phần `static` của cùng lớp trong khi nó chưa hoàn tất.

Theo **JLS `12.4.2 — Detailed Initialization Procedure**, mỗi class/interface `C` có một **initialization lock `LC`**. Việc JVM ánh xạ `C` tới lock thực tế như thế nào là chi tiết triển khai; không nên tự động đồng nhất `LC` với monitor của `C.class`.

Ba tình huống quyết định hành vi:

1. **Chưa khởi tạo:** một thread được ghi nhận là thread thực hiện initialization và chạy chuỗi khởi tạo.
2. **Đang được cùng thread khởi tạo:** nếu code trong `<clinit>` lại yêu cầu khởi tạo chính lớp đó, đây là **khởi tạo đệ quy trên cùng thread**; yêu cầu lặp **hoàn tất bình thường**, không chờ chính mình.
3. **Đang được thread khác khởi tạo:** thread yêu cầu phải **chờ** quá trình hiện tại kết thúc, sau đó kiểm tra lại trạng thái lớp. Nếu nhiều lớp khởi tạo phụ thuộc lẫn nhau giữa nhiều thread, một chu trình chờ có thể tạo **deadlock**.

```text
      Class C: chưa khởi tạo
                |
                | Thread T1 yêu cầu active use
                v
    C đang được khởi tạo bởi T1
         /              \
        /                \
 T1 yêu cầu C lần nữa    T2 yêu cầu C
        |                     |
  Trả về bình thường       Chờ T1
 (không chạy <clinit>       hoàn tất
  lần thứ hai)
        |
        v
 T1 tiếp tục chạy initializer bên ngoài
        |
        +-- thành công ---> C initialized, đánh thức thread chờ
        |
        +-- thất bại ----> C erroneous, đánh thức thread chờ
```

Điểm mấu chốt: **cơ chế khởi tạo tự bảo vệ khỏi yêu cầu đệ quy cùng thread**, nhưng **không có bảo đảm tự động ngăn mọi chu trình phụ thuộc giữa các thread khác nhau**.

## 2. Phân biệt Loading, Linking, Initialization và instance construction

Một class có thể đã được biết đến bởi runtime mà khối `static` của nó chưa từng chạy.

| Giai đoạn | Ý nghĩa khái quát | Có chạy `static` của class chưa? |
| --- | --- | --- |
| **Loading** | Tìm/định nghĩa biểu diễn class/interface runtime qua class loader | Không nhất thiết |
| **Linking: verification** | Kiểm tra cấu trúc và an toàn kiểu của class file | Không phải thực thi `static` |
| **Linking: preparation** | Chuẩn bị biến `static` và đặt giá trị mặc định theo quy tắc JVM | Không chạy biểu thức khởi tạo tùy ý |
| **Linking: resolution** | Xử lý symbolic references theo quy tắc liên kết | Không đồng nghĩa class initializer hoàn tất |
| **Initialization** | Thực thi các biểu thức khởi tạo `static` và khối `static { }` theo quy tắc JLS | Có |
| **Instance construction** | Cấp phát object và chạy `<init>` cho instance | Khác với `<clinit>` |

Class initialization thường liên quan phương thức đặc biệt **`<clinit>`** trong class file: compiler có thể gộp mã khởi tạo các static fields và static blocks thành một phương thức được JVM thực hiện theo quy tắc initialization. Không được hiểu `<clinit>` là constructor của từng instance.

```java
class Config {
    static int PORT = loadPort();

    static int loadPort() {
        return 8080;
    }

    Config() {
        // Constructor instance
    }
}
```

Đây là **mã minh họa class**, không phải một chương trình có `main`. Giá trị mặc định của `PORT` trong preparation là `0`; khi initialization thực thi biểu thức `loadPort()`, giá trị được gán thành `8080`. Việc tạo nhiều `new Config()` sau đó **không chạy lại class initializer**.

### Khi nào class initialization thường xảy ra?

Các thao tác chủ động sử dụng (*active use*) như:

- Tạo một instance của lớp bằng `new`.
- Gọi phương thức `static` khai báo bởi lớp.
- Đọc/ghi một trường `static` được khai báo bởi lớp, **trừ một số ngoại lệ về constant variables** theo JLS.
- Một số thao tác reflection có yêu cầu initialization.

Ngược lại, việc tham chiếu `SomeClass.class`, dùng `Class.forName(name, false, loader)`, hoặc tạo `new SomeClass[10]` **không nhất thiết khởi tạo `SomeClass`**. Trường `static final` là **compile-time constant variable** có thể được inline tại nơi dùng và không kích hoạt initialization của lớp khai báo khi đọc theo các quy tắc tương ứng.

**Cẩn thận:** khi một class được khởi tạo, superclass và những superinterfaces có khai báo default methods được khởi tạo theo trình tự mà JLS quy định nếu chưa được khởi tạo. Không đúng nếu nói “mọi interface mà class implements đều bắt buộc chạy initializer” hoặc “interface initialization luôn kéo theo mọi superinterface”.

## 3. Trạng thái khởi tạo và initialization lock `LC`

Mô hình trong JLS `12.4.2 giả định mỗi class/interface có trạng thái thể hiện một trong bốn tình huống:

1. **Verified and prepared, not initialized.**
2. **Initialization in progress** bởi một thread cụ thể.
3. **Fully initialized.**
4. **Erroneous state** vì quá trình khởi tạo không thể hoàn tất hợp lệ.

Những trạng thái này giúp phân biệt:

- Một class đã nạp nhưng vẫn chưa init.
- Một class đang init và có thread sở hữu hoạt động.
- Một class init thành công, có thể dùng theo quy tắc đồng bộ.
- Một class init lỗi và **không thể thử init lại một cách bình thường** trong cùng class identity.

### 3.1. Tóm tắt thuật toán theo JLS (giản lược có chủ đích)

Với class/interface `C` và thread yêu cầu `T`:

1. **Đồng bộ trên initialization lock `LC`**.
2. Nếu `C` đang init bởi **thread khác**, bỏ khóa và **chờ** thông báo quá trình đó kết thúc; sau đó kiểm tra lại trạng thái.
3. Nếu `C` đang init bởi **chính `T`**, đây là yêu cầu đệ quy: nhả khóa, **return bình thường** khỏi yêu cầu initialization lặp.
4. Nếu `C` **đã initialized**, nhả khóa và return bình thường.
5. Nếu `C` ở **erroneous state**, nhả khóa và ném `NoClassDefFoundError`.
6. Nếu chưa init, ghi nhận **`T` đang init `C`** và **nhả `LC`** trước khi chạy phần initialization còn lại.
7. Thực hiện các bước tiền khởi tạo liên quan constant variables, superclass và superinterfaces có default methods theo quy tắc, assertion status, sau đó chạy class/interface variable initializers và static initializer blocks theo thứ tự văn bản phù hợp.
8. Khi thành công, đồng bộ lại `LC`, chuyển trạng thái thành **initialized**, thông báo thread chờ và return bình thường.
9. Khi thất bại, xử lý throwable theo quy tắc (có thể bọc bởi `ExceptionInInitializerError`), gắn class thành **erroneous**, thông báo thread chờ và kết thúc bất thường.

Đây là **tóm lược phục vụ học tập**, không thay thế toàn văn thuật toán gồm các ngoại lệ và ràng buộc cụ thể của JLS.

### 3.2. Lock không nhất thiết bị giữ suốt lúc chạy khối `static`

Một chi tiết rất quan trọng: trong thuật toán JLS, thread **đánh dấu** mình đang khởi tạo lớp khi giữ `LC`, rồi **nhả lock** trước khi chạy superclass/default-interface initialization và body của static initializers.

Vậy vì sao thread khác vẫn phải chờ? Bởi JVM kiểm tra **trạng thái “initialization in progress by another thread”**; khi gặp trạng thái đó, thread đợi đến khi initialization hoàn tất.

Do đó cần phân biệt:

- **Initialization lock `LC`:** được dùng để điều phối chuyển trạng thái và thông báo.
- **Trạng thái “being initialized by T”:** cho JVM biết thread nào hiện chịu trách nhiệm.
- **Thời gian thực thi code initializer:** có thể chạy sau khi `LC` đã được nhả.

Không nên giảng rằng “Thread A giữ monitor `SomeClass.class` từ lúc vào đến lúc rời khối `static`” là nghĩa bắt buộc của đặc tả. JVM có quyền tối ưu/biến đổi cơ chế lock nếu giữ được tính đồng bộ và quan sát được mà đặc tả yêu cầu.

### 3.3. Tại sao không dùng `synchronized(SomeClass.class)` thay cho quy tắc init?

`SomeClass.class` là một `Class` object có thể được ứng dụng dùng làm monitor, nhưng JLS **không yêu cầu** initialization lock `LC` phải chính là monitor object đó. Đồng bộ trên `SomeClass.class` **không** là API quản lý trạng thái class initialization.

Ngoài ra, khi truy cập `SomeClass.class`, class literal không tự động buộc static initializer chạy. Vì vậy viết:

```java
synchronized (SomeClass.class) {
    // Đây là monitor do code ứng dụng dùng.
}
```

là **minh họa cú pháp synchronized**; nó không thay thế chính sách của JVM đối với `<clinit>`, cũng không là cách giải quyết deadlock phụ thuộc lớp một cách tổng quát.

## 4. Một thread khởi tạo, thread khác chờ — không chạy `<clinit>` hai lần

Giả sử hai thread gần như đồng thời gọi `Cache.get()` và `Cache` chưa init:

```text
Thread T1                            Thread T2
---------                            ---------
get Cache.value                     get Cache.value
    |                                    |
C chưa initialized                     C đang init bởi T1
    |                                    |
mark C initializing by T1              chờ trạng thái C thay đổi
    |
chạy Cache.<clinit>
    |
đặt static fields
    |
mark C initialized, notify
    |                                    |
đọc Cache.value                         tiếp tục, đọc Cache.value
```

Sau khi initialization hoàn tất thành công, cả hai thread có thể tiếp tục sử dụng lớp. JVM phải tuân thủ các quan hệ đồng bộ cần thiết của initialization; không được để thread chờ tiếp tục như thể class đã init thành công khi initializer vẫn đang thực thi dở.

### 4.1. Ví dụ Java 17+: chỉ một lần chạy initializer dù có hai thread

Tạo tệp **`ClassInitWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassInitWaitDemo {
    private static final CountDownLatch entered = new CountDownLatch(1);
    private static final CountDownLatch release = new CountDownLatch(1);
    private static final AtomicInteger runs = new AtomicInteger();

    static class Slow {
        static int value = initialize();

        static int initialize() {
            runs.incrementAndGet();
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            return 42;
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger first = new AtomicInteger();
        AtomicInteger second = new AtomicInteger();

        Thread t1 = new Thread(() -> first.set(Slow.value), "reader-1");
        t1.start();
        entered.await(); // Đợi t1 thực sự đi vào initializer.

        Thread t2 = new Thread(() -> second.set(Slow.value), "reader-2");
        t2.start();

        release.countDown(); // Cho phép initializer kết thúc.
        t1.join();
        t2.join();

        System.out.println("initializer runs: " + runs.get());
        System.out.println("first: " + first.get());
        System.out.println("second: " + second.get());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ClassInitWaitDemo.java
java ClassInitWaitDemo
```

**Stdout chính xác khi chương trình hoàn tất bình thường:**

```text
initializer runs: 1
first: 42
second: 42
```

Giải thích:

- Thread `t1` trở thành thread chịu trách nhiệm initialization của `Slow`.
- Nó tăng `runs` đúng một lần và chờ latch `release` trong initializer.
- Thread `t2` cùng truy cập `Slow.value`. Nếu tới trong lúc `Slow` chưa initialized, nó phải đợi JVM hoàn tất initialization; nếu tới sau khi `t1` hoàn tất, nó đọc giá trị sẵn có.
- Dù thứ tự scheduling giữa `t2` và việc release không cố định, **kết quả vẫn là một lần chạy initializer** và cả hai đọc 42 khi bình thường.

**Giới hạn minh họa:** latch đồng bộ trong chương trình là công cụ để dễ quan sát, **không phải initialization lock `LC` của JVM**. Không được suy luận JVM triển khai class initialization bằng `CountDownLatch`.

## 5. Khởi tạo đệ quy trên cùng thread: có thể nhìn thấy giá trị mặc định

Một static initializer có thể gián tiếp tham chiếu trở lại chính lớp đang được khởi tạo:

```text
T1 bắt đầu khởi tạo A
    |
    +→ A initializer cần B.value
                      |
                      +→ T1 bắt đầu khởi tạo B
                                         |
                                         +→ B initializer đọc A.value
                                                                    |
                                                                    +→ JVM thấy A đang init bởi T1
                                                                        → yêu cầu init A đệ quy return
                                                                        → B đọc A.value hiện thời
```

JLS quy định việc cùng thread yêu cầu khởi tạo lại class **đang được nó khởi tạo** thì yêu cầu đó hoàn tất bình thường. Nó **không** chạy lại `A.<clinit>` từ đầu và **không** tự chờ một việc mà chính thread ấy đang làm.

Hệ quả quan trọng: static field có thể được đọc khi nó vẫn giữ **giá trị mặc định từ preparation**, trước khi biểu thức khởi tạo trong source hoàn tất.

### 5.1. Ví dụ Java 17+ độc lập: vòng phụ thuộc A → B → A

Tạo **`RecursiveInitDemo.java`**:

```java
public class RecursiveInitDemo {
    static class A {
        static int value = calculate();

        static int calculate() {
            return B.value + 1;
        }
    }

    static class B {
        static int value = A.value + 10;
    }

    public static void main(String[] args) {
        System.out.println("A.value = " + A.value);
        System.out.println("B.value = " + B.value);
    }
}
```

Chạy:

```bash
javac --release 17 RecursiveInitDemo.java
java RecursiveInitDemo
```

**Stdout chính xác:**

```text
A.value = 11
B.value = 10
```

### 5.2. Diễn giải từng bước

Ban đầu, trong preparation, các `static int` mang giá trị mặc định **0**:

```text
A.value = 0   (chưa chạy biểu thức initializer)
B.value = 0   (chưa chạy biểu thức initializer)
```

Khi `main` đọc `A.value`:

1. Thread chính bắt đầu `A.<clinit>`.
2. `A.value = calculate()` cần `B.value`.
3. JVM bắt đầu `B.<clinit>` **trên cùng thread**.
4. `B.value = A.value + 10` đọc `A.value`, trong lúc `A` vẫn đang init bởi **thread chính**.
5. Yêu cầu init `A` lặp được JVM coi là recursive request cùng thread và **return bình thường**; trường `A.value` lúc này vẫn là **0**.
6. `B.value` nhận `0 + 10 = 10`; `B` hoàn tất initialization.
7. `A.calculate()` lấy `B.value = 10`, trả 11; `A.value` nhận 11; `A` hoàn tất.
8. `main` in `A.value = 11` và `B.value = 10`.

Điều này **không** phải race condition vì ví dụ chỉ dùng một thread cho chuỗi khởi tạo. Cũng không phải JVM “bỏ sót phép gán”: JVM cố ý xử lý yêu cầu init đệ quy cùng thread bằng cách không chờ, và giá trị mặc định có thể được đọc trước thời điểm biểu thức gán chạy xong.

### 5.3. Có luôn tránh được deadlock nếu tham chiếu vòng?

Không. Chỉ trường hợp **cùng thread** yêu cầu khởi tạo lại **cùng class đang được nó khởi tạo** mới có nhánh xử lý đệ quy như trên.

Nếu vòng phụ thuộc phân bố qua **hai thread**, thread này có thể cần một class đang được thread kia init, và ngược lại. Khi ấy mỗi thread phải chờ **thread khác**; JVM không thể chỉ dùng quy tắc “same-thread recursion” để giải quyết.

### 5.4. Đừng biến vòng phụ thuộc thành hợp đồng API

Nếu sửa code hoặc thay thứ tự gọi lần đầu, thời điểm initialization của A/B có thể đổi. Ví dụ việc đọc `B.value` trước `A.value` có thể tạo chuỗi kết quả khác với việc đọc A trước. Vì vậy code sản xuất không nên dựa vào “giá trị mặc định nhìn thấy giữa vòng init” như một hành vi nghiệp vụ mong muốn.

Để giảm rủi ro, tránh các initializer tĩnh truy cập qua lại giữa nhiều class khi có thể; xem xét khởi tạo sau bằng explicit initialization, dependency injection hoặc tạo đối tượng config độc lập với thứ tự tải lớp.

## 6. Deadlock khởi tạo lớp: hai thread chờ hai class khác nhau

Bây giờ xét hai class `Alpha` và `Beta` có static initializers tham chiếu qua lại:

```text
Thread T1                              Thread T2
---------                              ---------
bắt đầu Alpha.<clinit>                 bắt đầu Beta.<clinit>
Alpha: initializing by T1             Beta: initializing by T2
      |                                      |
      +→ cần Beta.value                      +→ cần Alpha.value
                |                                      |
                v                                      v
    Beta đang init bởi T2                  Alpha đang init bởi T1
                |                                      |
           T1 đợi T2                                 T2 đợi T1
                |                                      |
                +--------------- chu trình -------------+
```

Không thread nào có thể hoàn tất initializer của chính mình bởi cả hai đều đang chờ class của đối phương.

**Đây là class initialization deadlock**, không nhất thiết là deadlock thuần túy do hai ứng dụng cùng giữ các monitor `synchronized`. Việc initializer chạy sau khi JVM nhả `LC` không loại bỏ vấn đề, bởi trạng thái **“class đang được thread kia khởi tạo”** vẫn buộc thread còn lại phải chờ.

### 6.1. Vì sao JVM không tự cho thread T1 đọc dữ liệu Beta dở dang?

Cơ chế same-thread recursion chỉ cho phép **thread đang chịu trách nhiệm** tiếp tục khi nó yêu cầu init lại lớp của chính mình. Một thread khác không có cùng quyền đó: nó phải đợi quá trình init của class kết thúc theo quy tắc JLS.

Nếu JVM tùy ý cho T1 đọc `Beta.value` trước khi `Beta` init xong, nó phá hỏng hợp đồng đồng bộ hóa khởi tạo với các thread khác. Vì vậy giải pháp đúng là **tránh tạo chu trình phụ thuộc chéo giữa các initializer**, không ép JVM bỏ chờ.

### 6.2. Ví dụ Java 17+ tái hiện chu trình chờ với daemon threads

Thí nghiệm sau **cố tình tạo deadlock**. Không dùng mẫu này trong ứng dụng thật. Hai thread được đặt là **daemon** để khi thread `main` in kết quả và kết thúc, chương trình demo không bị giữ sống bởi chính hai thread bị kẹt. Mỗi class dùng `CountDownLatch` để bảo đảm **cả hai initializer đã bắt đầu** trước khi chúng truy cập static field của nhau.

Tạo tệp **`InitDeadlockDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InitDeadlockDemo {
    private static final CountDownLatch bothStarted = new CountDownLatch(2);

    static void rendezvous() {
        bothStarted.countDown();
        try {
            bothStarted.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    static class Alpha {
        static int value = initialize();

        static int initialize() {
            rendezvous();
            return Beta.value + 1;
        }
    }

    static class Beta {
        static int value = initialize();

        static int initialize() {
            rendezvous();
            return Alpha.value + 1;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = new Thread(() -> {
            int unused = Alpha.value;
        }, "alpha-initializer");

        Thread t2 = new Thread(() -> {
            int unused = Beta.value;
        }, "beta-initializer");

        t1.setDaemon(true);
        t2.setDaemon(true);

        t1.start();
        t2.start();

        bothStarted.await();
        t1.join(300);
        t2.join(300);

        System.out.println("both initializers started: true");
        System.out.println("both threads alive: "
                + (t1.isAlive() && t2.isAlive()));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 InitDeadlockDemo.java
java InitDeadlockDemo
```

**Stdout mong đợi trong môi trường thực thi thông thường:**

```text
both initializers started: true
both threads alive: true
```

Thời điểm hai thread được lập lịch không cố định, nên **không dùng số mili giây ở `join(300)` làm phép chứng minh deadlock tổng quát**. Tuy nhiên latch bảo đảm cả `Alpha` và `Beta` đều đã đi vào initializer trước khi chúng tham chiếu tới giá trị của lớp còn lại. Với tình huống này, mỗi bên chờ class do bên kia đang init.

Không nên chuyển `t1`/`t2` thành non-daemon nếu chỉ đang thử nghiệm: khi đó tiến trình có thể không kết thúc. Chỉ dùng demo trong môi trường học tập cô lập; sau khi thread chính kết thúc, runtime có thể kết thúc các daemon threads cùng tiến trình.

### 6.3. Vì sao `CountDownLatch` không phải nguồn gốc deadlock?

Hai lời gọi `rendezvous()` làm nhiệm vụ **đồng bộ điểm bắt đầu**: chúng chỉ chờ cho đến khi cả hai class initializers đã đến barrier, rồi cả hai được thả ra. Sau đó:

- `Alpha.initialize()` cần đọc `Beta.value`, trong khi `Beta` đang được T2 init.
- `Beta.initialize()` cần đọc `Alpha.value`, trong khi `Alpha` đang được T1 init.

Vòng chờ thực sự nằm ở **class initialization dependencies**. Bỏ latch ra có thể khiến một thread init cả hai lớp theo thứ tự và tránh deadlock tình cờ, làm test không tái hiện ổn định.

### 6.4. Có phải `ClassCircularityError` sẽ tự động xuất hiện?

**Không.** `ClassCircularityError` liên quan phát hiện vòng không hợp lệ trong **cấu trúc kế thừa/triển khai class hoặc interface** khi loading theo các quy tắc riêng. Vòng trong **static initializer execution** ở hai thread không mặc nhiên được chuyển thành `ClassCircularityError`.

Một JVM có thể hỗ trợ nhiều công cụ chẩn đoán thread và lock, nhưng **không nên giả định class initialization deadlock luôn được runtime tự phá vỡ hoặc luôn hiện trong mọi công cụ monitor-deadlock detection**. Khi cần điều tra, kết hợp thread dumps, các vị trí `<clinit>`, stack traces và trạng thái những classes phụ thuộc.

## 7. Vòng phụ thuộc cùng thread khác vòng chờ nhiều thread thế nào?

| Thuộc tính | Same-thread recursive initialization | Cross-thread initialization deadlock |
| --- | --- | --- |
| Ai đang init A? | T1 | T1 |
| Ai đang init B? | T1 | T2 |
| B cần A khi A chưa xong | T1 yêu cầu A đang init bởi chính T1 | T2 yêu cầu A đang init bởi T1 |
| Quy tắc JLS áp dụng | Recursive request cùng thread **return bình thường** | Yêu cầu từ thread khác **phải chờ** |
| Có nhất thiết bế tắc? | Không theo cơ chế chờ riêng này | Có thể bế tắc nếu tạo vòng T1 → T2 → T1 |
| Có thể thấy giá trị static mặc định? | Có, nếu field chưa được gán trong initializer | Thread khác không được tùy ý coi class đang init dở là fully initialized |
| Rủi ro chính | Trạng thái khởi tạo một phần; thứ tự truy cập gây kết quả bất ngờ | Thread không tiến triển, ứng dụng treo |
| Cách tránh | Giảm static dependencies đệ quy; tránh đọc field khi chưa set | Không tạo dependency cycle giữa initializers, đặc biệt khi chạy đa thread |

Một vòng tham chiếu trong **code** không nhất thiết gây deadlock. Kết quả phụ thuộc **thread nào khởi tạo class nào trước**, **tại lúc nào** và **đường gọi của initializer**.

## 8. Khi initialization thất bại: class có thể ở trạng thái erroneous

Không phải mọi initializer kết thúc thành công. Xét static field initializer gọi một phương thức ném exception:

```java
static int value = fail();
```

Khi một exception thông thường làm initialization hoàn tất bất thường, JLS yêu cầu xử lý throwable phù hợp, thường **bọc trong `ExceptionInInitializerError`**. Class/interface được đánh dấu ở **erroneous state**.

Những lần active-use tiếp theo của **chính runtime class đó** không đơn giản chạy lại static initializer; chúng thường dẫn tới **`NoClassDefFoundError`** liên quan việc không thể khởi tạo class.

### 8.1. Ví dụ Java 17+ chạy được: lần đầu lỗi, lần sau không thử lại

Tạo tệp **`FailedInitDemo.java`**:

```java
public class FailedInitDemo {
    static class Broken {
        static int value = initialize();

        static int initialize() {
            throw new IllegalStateException("bad configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.value);
            } catch (LinkageError error) {
                System.out.println("attempt " + attempt + ": "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 FailedInitDemo.java
java FailedInitDemo
```

**Stdout chính xác:**

```text
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
```

Giải thích:

1. Lần đầu đọc `Broken.value` khiến `Broken` được khởi tạo. `initialize()` ném `IllegalStateException`, được bọc thành `ExceptionInInitializerError` theo quy tắc vì throwable ban đầu không phải `Error`.
2. `Broken` được đánh dấu erroneous.
3. Lần thứ hai, JVM không chạy `initialize()` lại như thể chưa có gì xảy ra; active use dẫn đến `NoClassDefFoundError`.

**Lưu ý kỹ:** Nếu nguyên nhân initializer đã là một subtype của `Error`, cách truyền lỗi ở lần đầu có thể khác; không phải mọi initialization failure đều bắt buộc xuất hiện `ExceptionInInitializerError`. Nếu initialization của superclass thất bại, việc lan truyền cũng tuân theo các nhánh riêng trong JLS.

### 8.2. Khi nhiều thread đang chờ class lỗi

Nếu T1 đang init class C, T2/T3 đang đợi, rồi initializer của C kết thúc bất thường:

- JVM đánh dấu C **erroneous**.
- Những thread chờ được thông báo để kiểm tra lại trạng thái.
- Các yêu cầu sử dụng sau đó không biến C trở lại trạng thái “chưa init”; chúng gặp quy tắc lỗi phù hợp, thường `NoClassDefFoundError`.

Nên phân biệt **nguyên nhân gốc** ở lần khởi tạo đầu với **triệu chứng tiếp theo** trong log ở các thread khác.

### 8.3. Có thể “reset static initializer” bằng reflection không?

Không có API Java chuẩn để đặt một `Class` đang erroneous quay lại trạng thái “uninitialized” và chạy lại `<clinit>` theo ý muốn. Tạo **định nghĩa class mới bằng class loader khác** có thể dẫn đến class identity khác, nhưng đó là một runtime class khác với vòng đời/định danh riêng, không phải “repair” class cũ tại chỗ.

Đối với config có thể thay đổi sau startup, tránh đặt mọi thao tác kết nối bên ngoài và validate bất ổn vào `static initializer`. Thiết kế explicit initialization có kiểm soát thường dễ retry và giám sát lỗi hơn.

## 9. Các cơ chế liên quan: superclass, interface default methods và constant variables

### 9.1. Superclass initialization

Khi JVM khởi tạo một class, các superclass cần thiết được khởi tạo theo đúng trình tự (nếu chưa). Ví dụ:

```java
class Base {
    static {
        System.out.println("Base initialized");
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived initialized");
    }
}
```

Nếu active-use `Derived` trước và `Base` chưa init, thông thường `Base` được khởi tạo trước `Derived`. Đoạn này là **mã minh họa class**, chưa có `main` độc lập.

### 9.2. Interface có default methods

Trong Java hiện đại, initialization của một class cũng liên quan những **superinterfaces khai báo default methods** theo thuật toán JLS, không chỉ trực tiếp superclass. Đây là chi tiết thường bị bỏ qua khi debug trình tự `<clinit>`.

Ngược lại, **khởi tạo một interface** không tự động bắt mọi superinterface của nó phải được initialized chỉ vì có quan hệ kế thừa interface.

### 9.3. Compile-time constants

Ví dụ:

```java
class Constants {
    static final int LIMIT = 100;
    static final Integer BOXED = Integer.valueOf(100);
}
```

`LIMIT` là compile-time constant variable trong điều kiện thông thường và có thể được compiler inline. `BOXED` **không** phải constant variable theo cùng nghĩa, vì initializer không là constant expression của kiểu primitive/String theo JLS.

Đọc `Constants.LIMIT` từ nơi khác có thể không kích hoạt class initialization của `Constants`; đọc `Constants.BOXED` là một tình huống active use thích hợp. Vì vậy dùng compile-time constant để “kích hoạt static initialization” là cách làm không đáng tin.

## 10. Làm sao class loader ảnh hưởng phạm vi initialization?

Trong JVM, định danh runtime của class/interface gắn với **binary name + defining class loader**. Hai loader có thể định nghĩa hai class cùng binary name nhưng là **hai runtime types khác nhau**, mỗi type có trạng thái initialization riêng.

```text
("demo.Cache", LoaderA) → class A, init state A, lock LA
("demo.Cache", LoaderB) → class B, init state B, lock LB
```

Do đó:

- Mỗi định nghĩa class được JVM quản lý initialization của chính nó.
- Một application server/plugin host có thể có nhiều bản `demo.Cache` được định nghĩa bởi các loaders khác nhau.
- Static fields của hai runtime classes đó **không tự chia sẻ** dù binary name giống nhau.
- “Static field là global toàn JVM theo tên class” là một hiểu lầm.

Đây là lý do các vấn đề liên quan hot reload, plugin loaders và static singletons cần xét thêm class-loader boundaries.

**Không dựa vào việc dùng loader mới như giải pháp thông thường cho deadlock**: nó có thể tạo các type identity mới và nhiều ràng buộc liên kết/API phức tạp hơn. Tốt nhất là sửa thiết kế dependency của initializer.

## 11. Chẩn đoán tiến trình dường như bị treo trong `<clinit>`

Khi ứng dụng ngừng tiến triển lúc startup, không có exception rõ ràng, có thể nghi ngờ:

- Một static initializer đang thực hiện thao tác chậm/chờ I/O.
- T1 đang init class A, T2 yêu cầu A nên đợi hợp lệ.
- T1 và T2 tạo vòng chờ A ↔ B.
- Initializer giữ application lock rồi cần class khác, kết hợp với thread khác tạo vòng chờ hỗn hợp (monitor + class initialization).
- Static initializer gọi `Future.get()`, `join()`, `CountDownLatch.await()` hoặc API chờ tác vụ mà tác vụ đó lại yêu cầu class đang init.

### 11.1. Thu thập thread dump

Với HotSpot JDK có thể thử:

```bash
jcmd <pid> Thread.print
```

Trong nhiều môi trường cũng có thể dùng:

```bash
jstack <pid>
```

Các lệnh trên là **ví dụ thao tác chẩn đoán**, thay `<pid>` bằng PID thực tế của tiến trình Java. Lệnh `jcmd`/`jstack` thường thuộc bộ công cụ JDK; output và hỗ trợ có thể khác theo runtime/phiên bản.

Để điều tra:

1. Tìm thread đang chạy trong `<clinit>` hoặc phương thức do initializer gọi.
2. Tìm thread đang chờ class initialization, monitor, latch hoặc join.
3. Xác định quan hệ **class nào đang được thread nào init**.
4. Vẽ **wait-for graph**, ví dụ `T1 → Class B (T2)` và `T2 → Class A (T1)`.
5. Kiểm tra static field initializers, static blocks, dependency cycles, logging và I/O bên trong initializer.
6. Xác định cả class-loader identity nếu có nhiều loaders tạo classes trùng binary name.

### 11.2. Deadlock detector có thể không hiển thị hết vòng chờ

Một số công cụ tìm deadlock qua **monitor/ownable synchronizer**. Class initialization waiting có thể không xuất hiện giống một monitor lock thông thường trong mọi thread dump hoặc công cụ. Đừng kết luận “không deadlock” chỉ vì một báo cáo `findDeadlockedThreads()` trả null.

Sử dụng cả stack traces và thông tin class initialization. Trong trường hợp cần thiết, bổ sung logging trước/sau static initialization (trong môi trường kiểm thử) để xác định class nào không hoàn tất.

### 11.3. Ghi log class initialization đúng cách

Trên một số JVM HotSpot hiện đại, **Unified Logging** có các tag về class loading/initialization; chọn mức và tag được JVM thực tế hỗ trợ, kiểm tra bằng:

```bash
java -Xlog:help
```

Không áp đặt một tổ hợp tag/mức cố định cho mọi bản triển khai Java. Để điều tra, còn có thể log vòng đời của các thành phần ứng dụng **trước khi** active-use class thay vì nhét thêm logging phức tạp vào chính `<clinit>` và vô tình thay đổi timing của deadlock.

## 12. Cách thiết kế tránh phụ thuộc vòng trong static initializer

### 12.1. Tránh blocking operations trong `<clinit>`

Những hoạt động rủi ro khi đặt trực tiếp trong static initialization:

- Chờ network/database.
- Chờ một thread/task khác bằng `join()`, `Future.get()`, `await()`.
- Lấy nhiều locks theo thứ tự không thống nhất.
- Khởi tạo plugin/module khác vốn có thể tham chiếu ngược về lớp hiện tại.
- Đọc cấu hình có thể lỗi và khiến class chuyển erroneous, khó retry.

Không phải mọi tác vụ như vậy đều bị JVM cấm. Rủi ro nằm ở **cơ chế initialization được đồng bộ và có thể bị chờ bởi nhiều thread**.

### 12.2. Đồ thị phụ thuộc không vòng

Thay vì:

```text
A.<clinit> → B.<clinit> → A.<clinit>
```

hãy tách trách nhiệm:

```text
Config values
      |
      v
Service A        Service B
      \            /
       \          /
        explicit startup coordinator
```

Có thể xây các object trong một bước khởi tạo rõ ràng, có thứ tự, timeout và recovery policy. Các lớp không cần kéo nhau vào vòng static initializer trong quá trình tải.

### 12.3. Initialization-on-demand holder: dùng đúng phạm vi

Một idiom Java thường gặp:

```java
public final class Service {
    private Service() {}

    private static class Holder {
        static final Service INSTANCE = new Service();
    }

    public static Service getInstance() {
        return Holder.INSTANCE;
    }
}
```

Đây là **class minh họa**, không phải chương trình độc lập. Nó dựa vào class initialization để tạo singleton khi `Holder` được active-use lần đầu, theo cơ chế đồng bộ JVM.

Ưu điểm: khởi tạo trễ, không cần synchronized thủ công trong `getInstance()`, thread khác chờ đúng khi init đang tiến hành.

**Giới hạn:** Holder idiom **không** tự giải quyết vòng dependency giữa Holder và các classes khác; nếu constructor của `Service` gọi code khởi tạo lớp đang chờ ngược lại, vẫn có thể gặp bế tắc.

### 12.4. Explicit lifecycle và lỗi có thể thử lại

Với tài nguyên bên ngoài (database connections, clients, remote configuration), dùng startup lifecycle có timeout và trạng thái có thể retry, thay vì để toàn bộ kết nối nằm trong `static final`:

```java
final class ServiceManager {
    private volatile boolean ready;

    public synchronized void initialize() {
        // Nạp config, kết nối, kiểm tra dependency theo thứ tự rõ ràng.
        ready = true;
    }

    public boolean isReady() {
        return ready;
    }
}
```

Đoạn trên **chỉ minh họa hình dạng API**, chưa xử lý lỗi, nhiều lần gọi, idempotency, shutdown hoặc resource cleanup đầy đủ. Điểm học tập là: **quy trình explicit initialization có thể điều khiển** dễ quan sát và tái thử hơn class initializer thất bại khiến class thành erroneous.

### 12.5. Tránh xuất bản đối tượng chưa hoàn chỉnh từ initializer

Class initialization có bảo đảm đồng bộ riêng, nhưng **vòng cùng-thread** vẫn có thể nhìn thấy static field chưa được gán. Đừng xuất bản reference tới static state đang xây dựng dở qua các callback hoặc class phụ thuộc.

Nếu nhiều thành phần cần tham chiếu nhau, cân nhắc:

- Tách bước tạo đối tượng và bước nối dependencies.
- Dùng dependency injection hoặc factory.
- Thiết kế invariant được thiết lập hoàn chỉnh trước khi object được công bố.
- Viết tests cho thứ tự active-use khác nhau và các trường hợp concurrent startup.

## 13. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “JVM giữ `SomeClass.class` monitor suốt `<clinit>`.” | `LC` là lock khởi tạo theo đặc tả, ánh xạ tùy JVM; thủ tục đánh dấu trạng thái rồi nhả lock trước khi chạy phần khởi tạo còn lại. |
| “Thread khác có thể đọc static fields khi class đang init dở.” | Thread khác phải tuân theo quy tắc **chờ** class đang init bởi thread khác trước khi hoàn tất active-use. |
| “Tham chiếu vòng A → B → A luôn deadlock.” | Cùng thread xử lý recursive request bằng return bình thường; có thể thấy default values. |
| “Vòng A → B → A luôn an toàn.” | Nhiều thread có thể tạo chu trình chờ thật. |
| “Initialization lock là `synchronized(SomeClass.class)` của ứng dụng.” | Không có bảo đảm đó; đừng dùng monitor class literal như API thay thế. |
| “Static initializer luôn chỉ chạy khi `new` object.” | Static method/field active use và reflection có thể kích hoạt; tạo array của type không tự tạo instance. |
| “Truy cập `static final` luôn khởi tạo class.” | Compile-time constant variables có ngoại lệ. |
| “`ClassCircularityError` sẽ giải quyết static initialization deadlock.” | Không phải cơ chế chung cho vòng chờ giữa các static initializers. |
| “Một lần init lỗi, lần sau JVM tự thử lại.” | Runtime class ở erroneous state; các lần dùng sau thường gặp `NoClassDefFoundError`. |
| “`ExceptionInInitializerError` luôn là lỗi đầu tiên.” | Nếu throwable gốc là subtype của `Error` hoặc lỗi phát sinh ở superclass, đường lan truyền có thể khác. |
| “Static singleton mặc định shared toàn JVM bất kể class loader.” | Cùng binary name dưới loaders khác có thể là những runtime classes khác, mỗi class có static state riêng. |
| “Thread dump không ghi monitor deadlock thì không có initialization deadlock.” | Class-init waiting không luôn được công cụ phát hiện giống monitor deadlock. |
| “Holder idiom xử lý mọi vòng phụ thuộc.” | Nó chỉ giúp lazy init một trường hợp đơn giản, không tự loại bỏ dependency cycles. |
| “Thêm `Thread.sleep` trong `<clinit>` là cách ổn định concurrency.” | Sleep làm thay đổi scheduling, không thiết kế lại dependency và có thể che khuất vấn đề. |

## 14. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Hai thread cùng truy cập một trường `static` không phải compile-time constant của class chưa khởi tạo. JVM có chạy initializer hai lần song song không?

**Đáp án:** Không. Một thread chịu trách nhiệm khởi tạo runtime class; thread khác chờ hoặc nhận kết quả sau khi class đã initialized.

**Câu 2.** Vì sao thread hiện đang init A lại không tự deadlock khi trong initializer của A nó gián tiếp gọi A?

**Đáp án:** Theo JLS `12.4.2, nếu A đang được chính thread đó khởi tạo, yêu cầu initialization đệ quy **return bình thường**.

**Câu 3.** Trong `RecursiveInitDemo`, vì sao B nhận `A.value == 0`?

**Đáp án:** `A.value` đã có default value 0 từ preparation nhưng biểu thức `A.value = calculate()` chưa hoàn tất. Cùng thread được phép tiếp tục yêu cầu init đệ quy, nên B đọc giá trị hiện tại là 0.

**Câu 4.** Hai thread T1/T2 lần lượt init A/B; A cần B còn B cần A. Có thể xảy ra điều gì?

**Đáp án:** T1 chờ B do T2 đang init; T2 chờ A do T1 đang init. Đây là một **cross-thread class initialization deadlock**.

**Câu 5.** Khóa `LC` có bắt buộc chính là monitor của object `A.class`?

**Đáp án:** Không. Đặc tả cho phép JVM quyết định ánh xạ initialization lock. Không dùng `synchronized(A.class)` làm thay thế cơ chế init.

**Câu 6.** Thứ gì xảy ra khi class init bằng exception thường như `IllegalStateException`?

**Đáp án:** Lần đầu thường ném `ExceptionInInitializerError` bọc exception gốc và class bị đánh dấu erroneous; active-use sau thường dẫn đến `NoClassDefFoundError`.

**Câu 7.** Tạo `new SomeClass[10]` có chạy constructor của mười `SomeClass` không?

**Đáp án:** Không. Một array object được tạo, các phần tử tham chiếu ban đầu null.

**Câu 8.** Hai loaders riêng định nghĩa class cùng binary name. Chúng có chung initialization lock và static fields không?

**Đáp án:** Không mặc nhiên. Đây là hai runtime classes khác nhau, có trạng thái static và quá trình initialization riêng.

**Câu 9.** Holder idiom bảo đảm không deadlock dù singleton constructor gọi ngược lại nhiều lớp tĩnh khác?

**Đáp án:** Không. Nó chỉ là một hình thức lazy initialization dựa vào cơ chế JVM; dependency cycles vẫn có thể gây lỗi/bế tắc.

**Câu 10.** Vì sao class literal `SomeClass.class` không nên được dùng để ép static initializer chạy?

**Đáp án:** Class literal chỉ tạo/cung cấp `Class` object; không phải active-use bắt buộc chạy initializer của SomeClass theo các quy tắc tương ứng.

**Câu 11.** Tại sao class initialization lock quan trọng dù JVM vẫn có `synchronized` và `volatile` trong Java source?

**Đáp án:** JVM phải có cơ chế điều phối **khởi tạo class trước lần sử dụng cần thiết**, cả cho code sinh từ bytecode và nhiều thread. Đó là trách nhiệm runtime riêng, không yêu cầu mọi class phải tự khai báo monitor hay volatile field.

**Câu 12.** Chỉ thấy app startup treo mà không có `VerifyError`. Có thể là vấn đề initialization không?

**Đáp án:** Có. Bytecode vẫn có thể hợp lệ trong khi nhiều static initializers chờ lẫn nhau. Kiểm tra thread dumps, `<clinit>`, init dependencies và chỗ blocking.

## 15. Checklist vận hành và tổng kết

Khi viết hoặc kiểm tra class initialization:

1. Xác định các static field initializers và static blocks có thể kích hoạt class khác.
2. Vẽ quan hệ phụ thuộc A → B → C; chú ý chu trình quay về lớp ban đầu.
3. Đánh dấu các code path có thể chạy trên nhiều threads khi startup.
4. Tránh blocking I/O, `join`, `await` và đồng bộ khóa phức tạp trong `<clinit>`.
5. Đừng dựa vào thứ tự “vô tình” của lần active-use để đạt invariant.
6. Nếu init có thể lỗi vì yếu tố bên ngoài, cân nhắc explicit lifecycle với timeout/retry.
7. Khi thấy `ExceptionInInitializerError` hoặc `NoClassDefFoundError`, tìm **lần khởi tạo đầu tiên** và nguyên nhân gốc.
8. Khi thấy startup treo, thu thread dumps, lập wait-for graph, kiểm tra `<clinit>`.
9. Với plugin/application servers, xác định **defining class loader**, vì cùng tên class chưa chắc cùng class identity.
10. Kiểm thử cả thứ tự init, startup đồng thời và đường lỗi.

**Ba kết luận quan trọng nhất:**

- JVM đồng bộ hóa class initialization bằng trạng thái và initialization lock `LC`; thread khác có thể phải chờ lớp đang được thread hiện tại khởi tạo.
- Khởi tạo đệ quy **trong cùng thread** không tự chờ chính mình; có thể làm code quan sát default value của static field chưa được gán xong.
- Khởi tạo phụ thuộc vòng **giữa nhiều thread** có thể dẫn tới **deadlock thực sự**. Giải pháp bền vững nằm ở thiết kế dependency và lifecycle, không phải bỏ qua cơ chế đồng bộ của JVM.

### Tài liệu đặc tả chính thức

- [JLS 12.4.1 — When Initialization Occurs (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, superclass/default-interface initialization và constant variables.
- [JLS 12.4.2 — Detailed Initialization Procedure (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): initialization lock `LC`, trạng thái, same-thread recursion, wait/notify và failure.
- [JVMS 5.5 — Initialization (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization của class/interface ở cấp JVM.
- [JVMS 5.4 — Linking (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): phân biệt verification, preparation, resolution.
- [JLS 17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): đồng bộ, quan hệ visibility và Java Memory Model.
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): barrier dùng trong các thí nghiệm thread ở bài.
