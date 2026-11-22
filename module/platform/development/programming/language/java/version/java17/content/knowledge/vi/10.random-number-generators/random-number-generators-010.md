# Sinh số giả ngẫu nhiên trong Java 17: tránh dùng chung bộ sinh không an toàn giữa nhiều luồng

Chương trình Java thường cần số ngẫu nhiên để chọn mẫu, tạo dữ liệu kiểm thử, mô phỏng, phân phối công việc hoặc tạo token. Khi chương trình chạy trên nhiều luồng, cách sử dụng bộ sinh số ngẫu nhiên (random number generator, RNG) cần được thiết kế theo mô hình đồng thời.

Một đối tượng RNG có thể **không an toàn khi nhiều luồng cùng truy cập**, hoặc có thể an toàn nhưng tạo **tranh chấp và giảm hiệu năng** khi tất cả luồng dùng chung một trạng thái. Hai vấn đề này khác nhau. Java cung cấp nhiều lựa chọn như `Random`, `ThreadLocalRandom`, `SplittableRandom` và `SecureRandom`; mỗi loại phù hợp với mục đích riêng.

Bài học này tập trung vào cách tránh chia sẻ sai cách một RNG giữa nhiều luồng trong Java 17, đồng thời chọn đúng công cụ cho tác vụ thông thường, tính toán song song có thể tái lập và nhu cầu bảo mật.

## 1. RNG là gì và vì sao trạng thái của nó quan trọng?

Phần lớn API tạo số ngẫu nhiên trong Java tạo ra **số giả ngẫu nhiên** (pseudorandom). Một thuật toán bắt đầu từ trạng thái ban đầu (thường liên quan đến seed), sau đó cập nhật trạng thái để tạo ra dãy số có đặc tính thống kê phù hợp.

Mô hình đơn giản:

```text
Seed / trạng thái ban đầu
          |
          v
   Thuật toán RNG
          |
          v
      Số tiếp theo
          |
          v
   Cập nhật trạng thái
          |
          +------> số tiếp theo ...
```

Một instance RNG thường giữ trạng thái nội bộ. Khi gọi `nextInt()`, `nextLong()` hoặc `nextDouble()`, trạng thái đó được đọc và cập nhật.

Nếu hai luồng cùng dùng một instance:

```java
Random random = new Random();

Runnable job = () -> {
    int value = random.nextInt(100);
    System.out.println(value);
};

new Thread(job).start();
new Thread(job).start();
```

Hai luồng cùng gọi phương thức trên **một đối tượng**. Điều này đặt ra hai câu hỏi:

1. Các thao tác cập nhật trạng thái có được bảo vệ để không làm hỏng trạng thái RNG không?
2. Ngay cả khi an toàn, nhiều luồng có phải chờ hoặc tranh chấp trên cùng một trạng thái hay không?

Không phải mọi RNG đều có cùng câu trả lời. Cần biết hợp đồng thread-safety của lớp đang sử dụng thay vì đoán từ tên phương thức `next...()`.

## 2. Phân biệt thread-safety và hiệu năng đồng thời

Hai khái niệm thường bị đánh đồng:

| Khái niệm | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| **Thread-safe** | Có thể được nhiều luồng gọi đồng thời theo hợp đồng mà không làm hỏng trạng thái hoặc vi phạm tính đúng đắn được cam kết. | Dùng chung là hợp lệ về mặt an toàn, nhưng chưa chắc nhanh. |
| **Contention (tranh chấp)** | Nhiều luồng cùng cạnh tranh cập nhật hoặc truy cập một tài nguyên chung. | Có thể giảm throughput, tăng độ trễ và làm mất lợi ích của xử lý song song. |
| **Không thread-safe** | API không bảo đảm hoạt động đúng khi nhiều luồng cùng thao tác một instance. | Cần instance riêng cho từng luồng/tác vụ hoặc cơ chế đồng bộ phù hợp. |
| **Cryptographically secure** | Được thiết kế để tạo đầu ra phù hợp cho mục đích bảo mật, chống dự đoán theo mô hình đe dọa tương ứng. | Dùng khi cần token/nonce/secret; thường tốn tài nguyên hơn RNG thông thường. |

Ví dụ quan trọng: `java.util.Random` là **thread-safe**. Nó không phải lớp “hỏng ngay” khi chia sẻ giữa các luồng. Tuy nhiên, nhiều luồng dùng chung một `Random` có thể tranh chấp trên trạng thái nội bộ, vì vậy Java cung cấp `ThreadLocalRandom` cho các tình huống đa luồng thông thường.

Ngược lại, `SplittableRandom` được thiết kế cho việc dùng bởi một luồng tại một thời điểm; không chia sẻ cùng một instance cho nhiều luồng. Hãy tạo các instance độc lập bằng `split()` để phân phối cho những tác vụ riêng.

## 3. Random: an toàn khi chia sẻ nhưng có thể tranh chấp

`java.util.Random` là API lâu đời và vẫn được hỗ trợ trong Java 17:

```java
import java.util.Random;

Random random = new Random();
int number = random.nextInt(100); // 0 đến 99
double ratio = random.nextDouble(); // từ 0.0 đến nhỏ hơn 1.0
```

### 3.1. Random có thread-safe không?

Có. Hợp đồng của `Random` cho phép nhiều luồng sử dụng đồng thời cùng một instance. Việc cập nhật trạng thái được bảo vệ bằng cơ chế nguyên tử, nên các lần gọi không làm hỏng trạng thái RNG.

Điều này **không có nghĩa** dùng chung luôn là lựa chọn hiệu năng tốt. Nếu nhiều luồng liên tục gọi cùng một instance, chúng cạnh tranh cập nhật trạng thái. Các lần thử cập nhật có thể phải lặp lại khi có luồng khác cập nhật trước.

```java
Random shared = new Random();

Runnable task = () -> {
    long total = 0;
    for (int i = 0; i < 1_000_000; i++) {
        total += shared.nextInt(100);
    }
    System.out.println(total);
};

new Thread(task).start();
new Thread(task).start();
```

Đoạn mã trên có thể chạy an toàn về mặt thread-safety của `Random`, nhưng hai luồng vẫn chia sẻ một điểm cập nhật trạng thái. Khi số luồng và số lần gọi tăng lên, contention có thể trở thành nút thắt.

### 3.2. Tạo một Random cho từng luồng

Một cách giảm chia sẻ là mỗi luồng sở hữu một instance riêng:

```java
Runnable task = () -> {
    Random random = new Random();
    for (int i = 0; i < 5; i++) {
        System.out.println(Thread.currentThread().getName()
                + ": " + random.nextInt(100));
    }
};

new Thread(task, "worker-1").start();
new Thread(task, "worker-2").start();
```

Mỗi lần chạy `task`, biến `random` là biến cục bộ và instance chỉ được luồng đó sử dụng. Tuy nhiên, nếu tạo rất nhiều task ngắn hoặc dùng thread pool, việc tạo RNG trong từng task có thể không cần thiết; nhiều task có thể chạy lần lượt trên cùng worker thread.

`ThreadLocalRandom` thường là lựa chọn đơn giản hơn cho nhu cầu số giả ngẫu nhiên thông thường trên nhiều luồng.

## 4. ThreadLocalRandom: lựa chọn phổ biến cho đa luồng

`java.util.concurrent.ThreadLocalRandom` cung cấp một bộ sinh gắn với **luồng hiện tại**. Gọi `ThreadLocalRandom.current()` để lấy instance dành cho thread đang chạy:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(100);
double rate = ThreadLocalRandom.current().nextDouble();
```

Mỗi luồng sử dụng trạng thái RNG riêng, tránh để tất cả worker tranh chấp trên một instance `Random` dùng chung.

### 4.1. Sinh số trong khoảng

Các phương thức nhận cận dưới bao gồm và cận trên không bao gồm:

```java
ThreadLocalRandom random = ThreadLocalRandom.current();

int a = random.nextInt(1, 7);           // 1, 2, 3, 4, 5 hoặc 6
long b = random.nextLong(100L, 200L);   // 100 đến 199
double c = random.nextDouble(0.0, 1.0); // 0.0 <= c < 1.0
```

Nếu cận dưới lớn hơn hoặc bằng cận trên, các overload có cận sẽ ném `IllegalArgumentException`. Hãy xác định rõ khoảng mong muốn trước khi gọi.

### 4.2. Dùng với thread pool

Không cần truyền một đối tượng RNG chung vào từng task:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalRandomDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            for (int taskId = 0; taskId < 8; taskId++) {
                int id = taskId;
                pool.submit(() -> {
                    int value = ThreadLocalRandom.current()
                            .nextInt(1, 101);
                    System.out.println("Task " + id + ": " + value
                            + " on " + Thread.currentThread().getName());
                });
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Mỗi task gọi `current()` **trên chính worker thread đang thực thi task**. Nếu một worker chạy nhiều task khác nhau theo thời gian, các task đó dùng trạng thái thread-local của worker ấy; không có nghĩa mỗi task có một RNG mới.

### 4.3. ThreadLocalRandom không phải RNG bảo mật

`ThreadLocalRandom` được tối ưu cho việc sinh số giả ngẫu nhiên trong môi trường đồng thời. Không dùng nó để tạo:

- mật khẩu hoặc mã đặt lại mật khẩu;
- session ID, access token hoặc API key;
- nonce/secret dùng trong giao thức bảo mật;
- mã xác thực mà kẻ tấn công có thể dự đoán để chiếm quyền.

Với các mục đích đó, dùng `SecureRandom` và thiết kế quy trình bảo mật phù hợp.

### 4.4. Không đặt seed thủ công cho ThreadLocalRandom

`ThreadLocalRandom` quản lý seed/trạng thái theo luồng. API không hỗ trợ người dùng đặt seed theo cách thông thường; gọi `setSeed()` trên instance này không phải cách thiết kế để tái lập chuỗi số. Nếu cần dãy giả ngẫu nhiên có seed xác định cho mô phỏng hoặc kiểm thử, hãy cân nhắc `Random` hoặc `SplittableRandom` với seed được kiểm soát.

## 5. SplittableRandom: tách bộ sinh cho các tác vụ song song

`java.util.SplittableRandom` được thiết kế cho việc sinh số giả ngẫu nhiên trong tính toán song song. Instance không thread-safe; thiết kế chủ đạo là **một luồng dùng một instance**, sau đó tách instance con bằng `split()` cho các tác vụ độc lập.

```java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(12345L);
SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

int a = taskA.nextInt(100);
int b = taskB.nextInt(100);
```

`split()` tạo một generator mới có trạng thái riêng. Cần gọi việc tách trong một luồng sở hữu `root`, rồi phân phối `taskA` và `taskB` sao cho mỗi instance con chỉ được một luồng sử dụng tại một thời điểm.

### 5.1. Ví dụ phân phối generator cho hai tác vụ

```java
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SplittableRandomDemo {
    public static void main(String[] args) throws Exception {
        SplittableRandom root = new SplittableRandom(2026L);

        // Tách trước khi giao các instance cho worker.
        SplittableRandom randomA = root.split();
        SplittableRandom randomB = root.split();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> resultA =
                    pool.submit(() -> randomA.nextInt(1, 101));
            Future<Integer> resultB =
                    pool.submit(() -> randomB.nextInt(1, 101));

            System.out.println("A = " + resultA.get());
            System.out.println("B = " + resultB.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Mỗi generator con được giao cho một tác vụ riêng. Không đưa `root`, `randomA` hoặc `randomB` vào nhiều tác vụ chạy đồng thời. Nếu cần nhiều nhánh tính toán, tiếp tục tách generator trong luồng đang sở hữu generator cha trước khi phân phối.

### 5.2. Khi nào nên chọn SplittableRandom?

- Mô phỏng Monte Carlo hoặc tính toán số lượng lớn.
- Tác vụ song song cần generator riêng, tránh trạng thái chung.
- Cần điều khiển seed để thử nghiệm có thể tái lập theo cấu trúc phân chia công việc.
- Mỗi worker/task có thể sở hữu một RNG riêng trong suốt thời gian thực thi.

`SplittableRandom` không phải lựa chọn cho token bảo mật. Nó cũng không tự bảo đảm mọi chương trình song song cho ra kết quả y hệt giữa các lần chạy nếu thứ tự phân chia task, lịch chạy hoặc cách tiêu thụ số thay đổi. Tái lập kết quả đòi hỏi kiểm soát cả seed, cách split, cấu trúc task và thứ tự dùng các số.

## 6. SecureRandom: khi tính không thể dự đoán là yêu cầu bảo mật

`java.security.SecureRandom` tạo số giả ngẫu nhiên có tính chất phù hợp cho các ứng dụng bảo mật. Nó là lựa chọn cho token, nonce và giá trị bí mật khi được sử dụng đúng cách.

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        System.out.println(HexFormat.of().formatHex(token));
    }
}
```

`HexFormat` có từ Java 17. Mảng 32 byte cung cấp 256 bit dữ liệu ngẫu nhiên; cách dùng token thực tế vẫn cần cân nhắc entropy, thời hạn, lưu trữ, so sánh an toàn và giao thức xác thực.

### 6.1. Có thể chia sẻ SecureRandom giữa nhiều luồng không?

API `SecureRandom` được quy định là thread-safe. Một instance có thể được nhiều luồng sử dụng đồng thời theo hợp đồng của API. Tuy nhiên, hiệu năng và cách đồng bộ có thể phụ thuộc provider/implementation; đừng giả định mọi provider đều có cùng đặc tính throughput.

Trong nhiều ứng dụng, một instance được quản lý tập trung hoặc chia sẻ là cách dùng bình thường. Nếu hệ thống có tải rất lớn, hãy đo đạc bằng workload thực tế và xem xét cấu hình/provider thay vì tự tạo nhiều `SecureRandom` một cách tùy tiện. Việc khởi tạo nhiều instance không tự động làm tăng chất lượng ngẫu nhiên.

### 6.2. Không thay SecureRandom bằng Random để tăng tốc bảo mật

`Random`, `ThreadLocalRandom` và `SplittableRandom` phục vụ mục đích giả ngẫu nhiên thông thường, không được thiết kế để chống dự đoán trong mô hình tấn công. Một seed khó đoán hoặc seed lấy từ đồng hồ không biến các lớp này thành RNG bảo mật.

Nếu dữ liệu đầu ra có thể giúp kẻ tấn công xác định trạng thái hoặc dự đoán token kế tiếp, dùng API bảo mật như `SecureRandom`, đồng thời tuân thủ hướng dẫn của thư viện và giao thức.

## 7. Chọn đúng generator theo mục đích

| API | Thread-safety của instance | Mô hình sử dụng nên chọn | Mục đích phù hợp |
| --- | --- | --- | --- |
| `Random` | Thread-safe | Có thể chia sẻ; nếu nhiều luồng gọi thường xuyên, cân nhắc contention. | Tương thích mã hiện có, tác vụ đơn giản hoặc dãy có seed xác định. |
| `ThreadLocalRandom` | Generator gắn với luồng hiện tại | Mỗi worker lấy `ThreadLocalRandom.current()`. | Sinh số thông thường trong ứng dụng đa luồng. |
| `SplittableRandom` | Không thread-safe | Mỗi luồng/tác vụ sở hữu instance riêng; dùng `split()` để tạo nhánh. | Mô phỏng và tính toán song song, cần tách generator. |
| `SecureRandom` | Thread-safe theo API | Có thể chia sẻ; đánh giá provider và hiệu năng theo tải thực tế. | Token, nonce và dữ liệu cần tính khó dự đoán cho bảo mật. |

Không có một lớp RNG tốt nhất cho mọi tình huống. Chọn theo ba câu hỏi:

1. Có cần chống dự đoán bởi đối thủ không?
2. Instance có được nhiều luồng truy cập đồng thời không?
3. Có cần dãy kết quả tái lập để debug/mô phỏng không?

Nếu câu trả lời thứ nhất là có, ưu tiên `SecureRandom`. Nếu chỉ cần số giả ngẫu nhiên thông thường trong nhiều worker thread, `ThreadLocalRandom` là lựa chọn tự nhiên. Nếu cần phân chia generator cho các tác vụ song song độc lập, `SplittableRandom` phù hợp hơn. Nếu duy trì code cũ hoặc cần một instance `Random` có seed, có thể tiếp tục dùng `Random`, nhưng tránh biến nó thành điểm tranh chấp nóng.

## 8. API RandomGenerator có trong Java 17

Java 17 bổ sung các API mở rộng cho bộ sinh giả ngẫu nhiên theo JEP 356. `java.util.random.RandomGenerator` cung cấp một interface chung cho nhiều generator:

```java
import java.util.random.RandomGenerator;

RandomGenerator generator = RandomGenerator.getDefault();
int value = generator.nextInt(100);
double fraction = generator.nextDouble();
```

`RandomGenerator.getDefault()` trả về generator mặc định của runtime. Interface chung giúp code phụ thuộc vào các thao tác sinh số thay vì một class cụ thể.

Các generator khác nhau vẫn có hợp đồng và đặc tính riêng. Dùng interface `RandomGenerator` **không tự làm một instance trở nên thread-safe**. Hãy kiểm tra tài liệu của implementation được chọn trước khi chia sẻ nó giữa các luồng.

Ví dụ nhận generator làm tham số:

```java
import java.util.random.RandomGenerator;

static int rollDie(RandomGenerator random) {
    return random.nextInt(1, 7);
}
```

Hàm trên không quyết định generator nào được sử dụng. Người gọi có trách nhiệm cung cấp implementation và bảo đảm mô hình sở hữu/đồng thời đúng với loại generator đó.

### 8.1. Chọn generator theo tên bằng RandomGeneratorFactory

Java 17 cũng có `RandomGeneratorFactory` để truy vấn và tạo generator theo tên thuật toán:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator generator = factory.create(12345L);
System.out.println(generator.nextLong());
```

Tên thuật toán phải có trong runtime cụ thể. Có thể liệt kê các factory được hỗ trợ:

```java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
```

Đây là API hữu ích khi ứng dụng cần lựa chọn thuật toán có chủ đích. Không chọn tên chỉ dựa trên phỏng đoán; hãy kiểm tra thuật toán được runtime cung cấp và tài liệu của nó.

`RandomGenerator` là abstraction cho việc sinh số, không phải cam kết bảo mật chung. Nếu cần tính khó dự đoán, vẫn phải chọn `SecureRandom` và cơ chế phù hợp.

## 9. Các lỗi thiết kế đa luồng thường gặp

### 9.1. Chia sẻ một SplittableRandom cho mọi worker

Thiết kế sai:

```java
// Không dùng chung instance này giữa các luồng.
SplittableRandom shared = new SplittableRandom();

Runnable task = () -> {
    int value = shared.nextInt(100);
    System.out.println(value);
};
```

`SplittableRandom` không thread-safe. Nhiều luồng gọi `nextInt()` đồng thời trên cùng instance có thể làm hành vi không còn được bảo đảm theo hợp đồng lớp.

Sửa bằng cách tách generator trước khi giao:

```java
SplittableRandom root = new SplittableRandom(123L);
SplittableRandom forWorkerA = root.split();
SplittableRandom forWorkerB = root.split();
```

Sau đó chỉ giao mỗi instance con cho một worker sở hữu.

### 9.2. Dùng chung Random trong vòng lặp nóng

Thiết kế có thể đúng nhưng gây contention:

```java
Random shared = new Random();

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> shared.nextInt());
```

`Random` thread-safe, nhưng mọi worker cùng cập nhật trạng thái của một instance. Nếu cần random trong parallel stream, cân nhắc:

```java
IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> {
            int value = ThreadLocalRandom.current().nextInt();
            // Xử lý value
        });
```

Hoặc tổ chức generator `SplittableRandom` riêng cho từng tác vụ theo mô hình split. Việc chọn phương án nào còn phụ thuộc yêu cầu tái lập kết quả và cách chia công việc.

### 9.3. Tạo generator mới trong mọi lần gọi

Thiết kế kém hiệu quả:

```java
static int randomNumber() {
    return new Random().nextInt(100);
}
```

Nếu gọi hàng triệu lần, việc liên tục tạo đối tượng RNG là không cần thiết. Trong đa luồng, dùng `ThreadLocalRandom.current()` cho tác vụ thông thường; trong mô phỏng có seed, quản lý generator theo worker hoặc task.

### 9.4. Tự tạo seed từ đồng hồ cho từng luồng

Ví dụ dễ gây trùng seed:

```java
Random random = new Random(System.currentTimeMillis());
```

Nếu nhiều luồng khởi tạo gần như cùng thời điểm, seed có thể giống nhau hoặc có quan hệ dễ đoán, tùy cách tạo. Seed thời gian không phải nguồn entropy bảo mật và không đảm bảo các luồng có dãy độc lập.

Không cần tự xây dựng chiến lược seed thủ công cho `ThreadLocalRandom`. Với `SplittableRandom`, tạo một root generator rồi `split()` cho các nhánh. Với token bảo mật, dùng `SecureRandom` thay vì tự ghép thời gian, thread ID hoặc counter.

### 9.5. Nhầm thread-safe với cryptographically secure

`Random` thread-safe không có nghĩa đầu ra chống dự đoán. Tương tự, `ThreadLocalRandom` giảm contention nhưng không phải công cụ bảo mật. Chọn API theo **mục đích bảo mật**, không theo việc nó có hỗ trợ nhiều luồng hay không.

## 10. Ví dụ tổng hợp: sinh dữ liệu trong nhiều worker

Ví dụ sau dùng `ThreadLocalRandom` trong thread pool để tạo các số giả ngẫu nhiên thông thường:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;

public class ConcurrentRandomDemo {
    public static void main(String[] args) {
        int workerCount = 4;
        int tasks = 12;

        ExecutorService pool = Executors.newFixedThreadPool(workerCount);
        try {
            for (int i = 0; i < tasks; i++) {
                int taskId = i;
                pool.submit(() -> {
                    ThreadLocalRandom random = ThreadLocalRandom.current();
                    int quantity = random.nextInt(1, 51);
                    System.out.printf(
                            "task=%d, worker=%s, quantity=%d%n",
                            taskId,
                            Thread.currentThread().getName(),
                            quantity
                    );
                });
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ConcurrentRandomDemo.java
java ConcurrentRandomDemo
```

Mỗi lần chạy, thứ tự task, worker và các giá trị có thể khác nhau. Đây là điều bình thường trong chương trình đồng thời. `ThreadLocalRandom` giải quyết việc dùng generator theo luồng; nó không làm cho lịch chạy của thread pool trở nên xác định.

### Nếu cần kết quả có thể tái lập

Trong kiểm thử hoặc mô phỏng, đôi khi muốn cùng một seed tạo cùng dãy số. Khi đó, dùng generator có seed xác định và cấp quyền sở hữu rõ ràng:

```java
SplittableRandom root = new SplittableRandom(2026L);
SplittableRandom generatorForA = root.split();
SplittableRandom generatorForB = root.split();
```

Để kết quả có thể tái lập giữa các lần chạy, ngoài seed còn phải giữ nguyên cách split, cách phân phối task, thứ tự tiêu thụ số và thuật toán. Nếu task được phân công động cho worker theo lịch chạy không xác định, việc gắn kết quả với từng task có thể thay đổi dù tổng nguồn generator có seed cố định.

## 11. Hiểu đúng Math.random()

`Math.random()` là API tiện lợi trả về một `double` giả ngẫu nhiên trong khoảng từ `0.0` (bao gồm) đến `1.0` (không bao gồm):

```java
double value = Math.random();
int die = (int) (Math.random() * 6) + 1;
```

Đối với mã đơn giản, ít yêu cầu kiểm soát generator, cách này có thể đủ. Nhưng khi cần lựa chọn thuật toán, seed, phạm vi rõ ràng hoặc hiệu năng đa luồng, nên dùng API RNG cụ thể. `Math.random()` không phải API bảo mật và không nên được chọn để tạo token.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nhiều luồng dùng chung `SplittableRandom` | Instance không thread-safe. | Tạo generator riêng cho từng worker/task; dùng `split()` để tách. |
| Dùng chung `Random` chạy đúng nhưng throughput thấp | Một trạng thái RNG chung có thể gây contention. | Dùng `ThreadLocalRandom` cho random thông thường trong đa luồng hoặc tách generator theo task. |
| Dùng `ThreadLocalRandom` nhưng cần seed để tái lập | API quản lý trạng thái theo thread và không hỗ trợ đặt seed theo cách thông thường. | Dùng `Random` hoặc `SplittableRandom` với seed kiểm soát. |
| Dùng `Random` để tạo token bảo mật | RNG thông thường không được thiết kế để chống dự đoán. | Dùng `SecureRandom`. |
| Tạo `new Random()` liên tục trong vòng lặp | Tạo đối tượng không cần thiết và không giải quyết tốt mô hình đồng thời. | Quản lý RNG theo worker hoặc dùng `ThreadLocalRandom.current()`. |
| Các task nhận chuỗi số khác nhau giữa các lần chạy | Lịch chạy, thứ tự tiêu thụ số hoặc cách chia task thay đổi. | Kiểm soát seed và cả cấu trúc chia công việc nếu cần tái lập. |
| Tự seed bằng timestamp cho từng luồng | Seed có thể trùng hoặc dễ đoán. | Dùng cơ chế seed/split của RNG phù hợp; dùng `SecureRandom` cho bảo mật. |
| Nghĩ `RandomGenerator` tự thread-safe | Interface chung không xóa hợp đồng riêng của implementation. | Đọc tài liệu thread-safety của generator thực tế. |
| Khởi tạo nhiều `SecureRandom` với hy vọng luôn nhanh hơn | Khởi tạo/seed có chi phí và phụ thuộc provider. | Đo tải thực tế; dùng `SecureRandom` đúng API và chính sách bảo mật. |

## 13. Bài tập tự luyện

### Bài 1 — Phân biệt an toàn và hiệu năng

Một ứng dụng có 16 worker thread. Tất cả gọi `nextInt()` trên một instance `Random`.

1. Cách dùng này có được `Random` bảo đảm thread-safe không?
2. Có thể phát sinh contention không?
3. API nào phù hợp hơn nếu chỉ cần số giả ngẫu nhiên thông thường?

**Gợi ý:** `Random` thread-safe, nhưng instance dùng chung có thể tranh chấp trạng thái. Cân nhắc `ThreadLocalRandom.current()`.

### Bài 2 — Sửa cách dùng SplittableRandom

Đoạn mã sau không phù hợp:

```java
SplittableRandom random = new SplittableRandom();

Runnable task = () -> {
    System.out.println(random.nextInt(100));
};
```

Hãy tạo một generator gốc, tách hai generator con bằng `split()`, rồi giao mỗi generator con cho một task riêng. Giải thích vì sao không được để hai task cùng dùng một generator con.

### Bài 3 — Chọn API theo yêu cầu

Chọn API phù hợp nhất cho mỗi tình huống:

| Tình huống | Lựa chọn tham khảo |
| --- | --- |
| Sinh số ngẫu nhiên cho mỗi request trên thread pool | `ThreadLocalRandom` |
| Chia generator cho các nhánh mô phỏng song song | `SplittableRandom` |
| Tạo token ngẫu nhiên dùng trong xác thực | `SecureRandom` |
| Mã cũ cần một generator có seed xác định | `Random` hoặc generator có seed phù hợp |

Hãy giải thích thêm vì sao không thể thay `SecureRandom` bằng `ThreadLocalRandom` chỉ vì API thứ hai thuận tiện hơn trong môi trường đa luồng.

### Bài 4 — Tìm nguyên nhân dãy số khó tái lập

Một parallel stream dùng `SplittableRandom` nhưng kết quả gắn với từng phần tử thay đổi giữa các lần chạy. Hãy liệt kê những yếu tố cần kiểm soát: seed ban đầu, thứ tự split, cách gán nhánh cho task, thứ tự gọi generator và cách xử lý kết quả.

### Bài 5 — Dùng abstraction RandomGenerator

Viết một phương thức nhận `RandomGenerator` và sinh số từ 1 đến 6. Gọi nó bằng một generator có seed xác định, rồi giải thích vì sao abstraction chung không tự quyết định generator đó có được chia sẻ giữa nhiều luồng hay không.

## 14. Ghi nhớ khi thiết kế RNG cho chương trình nhiều luồng

- Trước khi chia sẻ một generator, hãy xác định instance đó có **thread-safe** hay không.
- `Random` thread-safe, nhưng một instance chung có thể trở thành điểm contention khi nhiều worker gọi liên tục.
- `ThreadLocalRandom.current()` là lựa chọn thông dụng cho số giả ngẫu nhiên không phục vụ bảo mật trong code đa luồng.
- `SplittableRandom` không thread-safe; mỗi luồng/tác vụ cần sở hữu generator riêng, thường tạo bằng `split()`.
- `SecureRandom` dành cho nhu cầu bảo mật và thread-safe theo API; đánh giá provider và hiệu năng bằng tải thực tế.
- Seed có thể giúp tái lập dãy số, nhưng tái lập kết quả của chương trình song song còn phụ thuộc cách chia và tiêu thụ số.
- `RandomGenerator` là abstraction, không phải lời hứa rằng mọi implementation có cùng thread-safety hoặc mức bảo mật.
- Không dùng timestamp, thread ID hoặc bộ đếm làm cách thay thế tùy tiện cho `SecureRandom` khi tạo bí mật.

### Tài liệu tham khảo

- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html) — hợp đồng thread-safety và các phương thức sinh số của `Random`.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html) — generator gắn với luồng hiện tại.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html) — generator không thread-safe và cơ chế `split()`.
- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) — API tạo số ngẫu nhiên phục vụ bảo mật.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html) — abstraction chung cho các generator trong Java 17.
- [JEP 356: Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356) — các API generator được bổ sung trong Java 17.
