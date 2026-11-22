# Tái hiện thí nghiệm bằng thuật toán, seed và thứ tự gọi trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** Sinh số giả ngẫu nhiên  
> **Mục tiêu:** Thiết kế chương trình sinh số giả ngẫu nhiên có thể phát lại kết quả bằng cách xác định thuật toán, seed và thứ tự gọi; hiểu ảnh hưởng của trạng thái bộ sinh, luồng song song và lựa chọn API trong Java 17.

## 1. Vì sao cùng một chương trình có thể cho kết quả ngẫu nhiên khác nhau?

Khi viết chương trình mô phỏng, kiểm thử, tạo dữ liệu mẫu hoặc chạy thí nghiệm, ta thường cần các giá trị trông có vẻ ngẫu nhiên:

- Sinh dữ liệu người dùng giả lập.
- Chọn mẫu ngẫu nhiên trong tập dữ liệu.
- Mô phỏng xúc xắc, hàng đợi, thời gian chờ hoặc xác suất lỗi.
- Khởi tạo trọng số trong thuật toán tối ưu.
- Tạo nhiễu để đánh giá độ bền của mô hình.

Ví dụ:

```java
import java.util.Random;

public class RandomDemo {
    public static void main(String[] args) {
        Random random = new Random();
        System.out.println(random.nextInt(100));
    }
}
```

Mỗi lần chạy, chương trình có thể in ra số khác nhau vì constructor không tham số của Random tự khởi tạo seed. Điều này hữu ích khi muốn các lần chạy độc lập, nhưng gây khó khăn khi cần tái hiện một lỗi hoặc so sánh hai phiên bản thuật toán.

Để **tái hiện thí nghiệm**, cần kiểm soát ít nhất ba yếu tố:

1. **Thuật toán (algorithm):** lớp/bộ sinh nào tạo ra chuỗi số giả ngẫu nhiên?
2. **Seed:** trạng thái khởi đầu được khởi tạo từ giá trị nào?
3. **Thứ tự gọi (call sequence):** những phương thức sinh số được gọi theo thứ tự nào, với tham số nào?

Chỉ lưu seed mà không ghi lại thuật toán và luồng gọi chưa đủ để đảm bảo tái hiện. Hai bộ sinh khác nhau nhận cùng một seed thường tạo ra hai chuỗi khác nhau; cùng một bộ sinh nhưng chương trình gọi thêm một lần nextInt() trước bước lấy mẫu cũng làm các giá trị sau đó thay đổi.

## 2. PRNG là gì? Seed có vai trò gì?

**PRNG (Pseudo-Random Number Generator)** là bộ sinh số giả ngẫu nhiên. Nó sử dụng một trạng thái ban đầu và một thuật toán xác định để tạo ra chuỗi giá trị có đặc tính thống kê giống ngẫu nhiên trong phạm vi thiết kế.

Với một thuật toán xác định:

```text
seed + thuật toán + trạng thái gọi
                  |
                  v
          chuỗi giá trị giả ngẫu nhiên
```

Nếu khởi tạo hai bộ sinh cùng thuật toán bằng cùng seed, rồi thực hiện cùng chuỗi lời gọi theo cùng thứ tự, chúng có thể tái tạo cùng chuỗi kết quả theo hợp đồng của bộ sinh đó.

### 2.1. Seed không phải là số ngẫu nhiên đầu ra

Seed là dữ liệu dùng để khởi tạo trạng thái của PRNG. Ví dụ:

```java
Random random = new Random(20261115L);
```

20261115L là seed. Nó không có nghĩa giá trị đầu tiên trả về sẽ là 20261115. Bộ sinh biến đổi seed qua thuật toán nội bộ rồi mới tạo ra số.

Bạn có thể chọn bất kỳ seed cố định nào cho một thí nghiệm. Điều quan trọng là lưu lại chính xác seed đó, kiểu dữ liệu và cách khởi tạo.

### 2.2. Cùng seed không có nghĩa mọi generator tạo cùng chuỗi

```java
Random first = new Random(12345L);
Random second = new Random(12345L);

System.out.println(first.nextInt());
System.out.println(second.nextInt());
```

Hai đối tượng cùng lớp Random và cùng seed sẽ cho cùng kết quả ở lời gọi tương ứng.

Nhưng không thể suy ra rằng:

```java
Random random = new Random(12345L);
SplittableRandom split = new SplittableRandom(12345L);
```

sẽ tạo cùng chuỗi. Random và SplittableRandom dùng thuật toán và trạng thái nội bộ khác nhau. **Seed chỉ có ý nghĩa cùng với thuật toán cụ thể.**

### 2.3. Vì sao không nên dùng thời gian hiện tại làm seed của thí nghiệm?

Ví dụ:

```java
Random random = new Random(System.currentTimeMillis());
```

Mỗi lần chạy ở thời điểm khác nhau sẽ thường có seed khác nhau. Nếu một lỗi xuất hiện trong lần chạy đó, chỉ lưu log đầu ra mà không lưu seed sẽ khó phát lại chính xác.

Đối với thí nghiệm cần tái hiện, hãy nhận seed từ cấu hình hoặc tham số dòng lệnh:

```java
long seed = 20261115L;
Random random = new Random(seed);
```

Nếu mục đích là tạo chuỗi khác nhau cho mỗi lần chạy, seed tự động có thể phù hợp. Nhưng cần ghi lại seed được sử dụng nếu sau này vẫn muốn tái hiện lần chạy cụ thể.

## 3. java.util.Random: bộ sinh quen thuộc với thuật toán được đặc tả

java.util.Random là lựa chọn đơn giản và có hợp đồng lâu đời. Java đặc tả thuật toán của lớp này để cùng seed và cùng chuỗi lời gọi tạo cùng chuỗi số trên các implementation Java phù hợp.

### 3.1. Khởi tạo bằng seed cố định

```java
import java.util.Random;

public class ReproducibleRandom {
    public static void main(String[] args) {
        long seed = 12345L;
        Random random = new Random(seed);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

Mỗi lần chạy chương trình, với cùng Java API và cùng thứ tự gọi, năm số được tạo ra sẽ giống nhau. Nếu tạo lại đối tượng:

```java
Random firstRun = new Random(12345L);
Random replay = new Random(12345L);

for (int i = 0; i < 5; i++) {
    int a = firstRun.nextInt(100);
    int b = replay.nextInt(100);
    System.out.println(a == b);
}
```

Kết quả gồm năm dòng true.

### 3.2. Random sử dụng LCG 48-bit

Để hiểu tại sao thứ tự gọi quan trọng, có thể xem cơ chế cốt lõi của Random. Nó dùng một dạng **Linear Congruential Generator (LCG)** với trạng thái 48-bit.

Các hằng số được đặc tả:

```java
private static final long multiplier = 0x5DEECE66DL;
private static final long addend = 0xBL;
private static final long mask = (1L << 48) - 1;
```

Khi khởi tạo bằng seed s, trạng thái nội bộ được đặt theo công thức:

```java
state = (s ^ multiplier) & mask;
```

Mỗi bước sinh bit cập nhật trạng thái:

```java
state = (state * multiplier + addend) & mask;
```

Sau đó lấy các bit cao của trạng thái làm kết quả trung gian. Các phương thức nextInt, nextLong, nextDouble và các phương thức khác sử dụng cơ chế này theo quy tắc riêng.

Đây là thuật toán xác định. Cùng trạng thái và cùng số bước cập nhật sẽ tạo cùng chuỗi trạng thái. Vì vậy, một lời gọi sinh số được chèn thêm có thể làm những kết quả tiếp theo dịch chuyển.

**Lưu ý:** Đây là mô tả thuật toán nội bộ đã được đặc tả của java.util.Random, không phải hướng dẫn tự viết lại PRNG trong ứng dụng. Hãy dùng API chính thức.

### 3.3. Seed long nhưng trạng thái của Random là 48-bit

Mặc dù constructor nhận long, thuật toán LCG của Random chỉ giữ trạng thái 48-bit. Việc biến đổi seed và mask có nghĩa một số giá trị seed khác nhau có thể ánh xạ vào cùng trạng thái khởi đầu.

Vì vậy:

- Seed là mã nhận diện lần chạy do ứng dụng quản lý, không phải khóa mật mã.
- Không nên coi hai seed long khác nhau chắc chắn tạo hai trạng thái nội bộ khác nhau.
- Nếu cần generator có trạng thái lớn hơn hoặc đặc tính thống kê khác, hãy cân nhắc API generator của Java 17.

### 3.4. Dùng nextInt(bound) thay cho phép chia dư

Khi muốn sinh số nguyên trong khoảng 0 đến bound - 1, nên dùng:

```java
int index = random.nextInt(10); // 0..9
```

Không nên tự viết:

```java
int index = Math.abs(random.nextInt()) % 10; // Không nên
```

Phép chia dư có thể tạo phân phối lệch vì miền số nguyên có dấu không chia hết cho 10; Math.abs(Integer.MIN_VALUE) còn là trường hợp đặc biệt không thể trở thành số dương trong kiểu int. nextInt(bound) xử lý giới hạn và tránh modulo bias theo hợp đồng của API.

## 4. Thứ tự gọi quyết định vị trí mỗi giá trị trong chuỗi

Một PRNG thông thường có trạng thái thay đổi sau mỗi lần gọi. Vì vậy, cùng seed nhưng thay đổi thứ tự gọi sẽ làm kết quả gắn với từng biến khác đi.

### 4.1. Hai lần chạy có cùng seed nhưng khác thứ tự gọi

```java
import java.util.Random;

public class CallOrderDemo {
    public static void main(String[] args) {
        long seed = 99L;

        Random first = new Random(seed);
        int firstA = first.nextInt(100);
        int firstB = first.nextInt(100);

        Random second = new Random(seed);
        int secondB = second.nextInt(100);
        int secondA = second.nextInt(100);

        System.out.println("firstA  = " + firstA);
        System.out.println("firstB  = " + firstB);
        System.out.println("secondB = " + secondB);
        System.out.println("secondA = " + secondA);
    }
}
```

Ở lần đầu, số đầu tiên được gán cho firstA và số thứ hai cho firstB. Ở lần thứ hai, cùng hai số đó được gán cho các biến theo thứ tự ngược lại. Vì thế, seed giống nhau nhưng **ý nghĩa dữ liệu gắn với mỗi giá trị** đã thay đổi.

### 4.2. Thêm một lời gọi ở giữa làm lệch các giá trị phía sau

```java
Random original = new Random(7L);
int a1 = original.nextInt(100);
int b1 = original.nextInt(100);

Random changed = new Random(7L);
int a2 = changed.nextInt(100);
int ignored = changed.nextInt(); // Lời gọi mới
int b2 = changed.nextInt(100);
```

a1 và a2 giống nhau vì đều là lời gọi đầu tiên. Nhưng b1 và b2 thường khác nhau: changed đã tiến thêm trạng thái trước khi sinh giá trị thứ hai.

Một thay đổi tưởng nhỏ trong code cũng có thể làm mất khả năng tái hiện:

- Thêm một giá trị random để ghi log hoặc debug.
- Thêm nhánh điều kiện đôi khi gọi thêm nextInt.
- Đổi thuật toán lấy mẫu làm số lần gọi generator thay đổi.
- Thêm một bước khởi tạo dữ liệu dùng chung generator trước khi chạy thí nghiệm.

### 4.3. Thứ tự tham số cũng là một phần của thí nghiệm

Các phương thức bounded như nextInt(bound) có thể tiêu thụ số bit khác nhau tùy bound và quá trình rejection sampling. Do đó, thay:

```java
int a = random.nextInt(10);
```

bằng:

```java
int a = random.nextInt(1000);
```

không chỉ đổi miền kết quả; nó có thể làm thay đổi trạng thái tiếp theo được dùng trong chuỗi. Để phát lại thí nghiệm, cần giữ cả **loại phương thức và tham số**.

## 5. Ví dụ thực hành: Tái hiện một thí nghiệm nhiều bước

Giả sử ta mô phỏng một lượt chạy có ba bước:

1. Chọn số lượng yêu cầu.
2. Chọn độ trễ giả lập.
3. Quyết định một yêu cầu có lỗi hay không.

Tạo file ExperimentDemo.java:

```java
import java.util.Random;

public class ExperimentDemo {

    static void runExperiment(long seed) {
        Random random = new Random(seed);

        int requestCount = 10 + random.nextInt(11);
        int delayMillis = 50 + random.nextInt(451);
        boolean failed = random.nextDouble() < 0.1;

        System.out.println("seed=" + seed);
        System.out.println("requestCount=" + requestCount);
        System.out.println("delayMillis=" + delayMillis);
        System.out.println("failed=" + failed);
    }

    public static void main(String[] args) {
        runExperiment(20261115L);
        System.out.println("--- replay ---");
        runExperiment(20261115L);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ExperimentDemo.java
java ExperimentDemo
```

Hai khối kết quả sẽ giống nhau vì mỗi lần gọi runExperiment đều:

- Khởi tạo một Random mới với cùng seed.
- Thực hiện cùng phương thức sinh số.
- Truyền cùng giới hạn.
- Gọi các phương thức theo cùng thứ tự.

Nếu sau này thêm một lần gọi random trước delayMillis, kết quả của bước trễ và quyết định lỗi sẽ thay đổi. Đó là lý do nên quản lý chuỗi gọi như một phần của thiết kế thí nghiệm.

### 5.1. Tách generator theo từng mục đích

Nếu một thí nghiệm có nhiều thành phần độc lập, có thể tạo generator riêng cho từng thành phần:

```java
long masterSeed = 20261115L;

Random requestGenerator = new Random(masterSeed);
Random delayGenerator = new Random(masterSeed + 1);
Random failureGenerator = new Random(masterSeed + 2);
```

Khi đó, thêm một lần gọi vào requestGenerator không làm dịch chuỗi của delayGenerator hay failureGenerator.

Đây là cách đơn giản để giảm sự phụ thuộc giữa các phần. Trong ứng dụng lớn, cần quy định cách tạo seed con rõ ràng, tránh dùng những giá trị tùy tiện hoặc có thể trùng. Có thể dùng SplittableRandom để tách generator có cấu trúc hoặc một hàm trộn seed được đặc tả trong dự án.

### 5.2. Ghi metadata để có thể phát lại

Một kết quả thí nghiệm nên lưu thông tin tối thiểu:

| Trường | Ví dụ | Lý do |
|---|---|---|
| seed | 20261115 | Khôi phục trạng thái khởi đầu |
| algorithm | java.util.Random | Xác định PRNG được dùng |
| javaVersion | 17.0.x | Ghi môi trường runtime |
| experimentVersion | experiment-v3 | Nhận biết logic thí nghiệm |
| inputDataset | dataset-2026-11 | Cố định dữ liệu đầu vào |
| callProtocol | request → delay → failure | Ghi thứ tự và tham số gọi |
| parallelism | 1 | Ghi chiến lược thực thi |

Ví dụ log:

```text
experiment=load-test
experimentVersion=v3
algorithm=java.util.Random
seed=20261115
javaVersion=17.0.x
callProtocol=requestCount:nextInt(11);delay:nextInt(451);failure:nextDouble()
parallelism=1
dataset=dataset-2026-11
```

Giá trị phiên bản ở đây là placeholder minh họa; hãy ghi giá trị thực từ runtime. Log seed và call protocol sẽ hữu ích hơn nhiều so với chỉ ghi các con số đầu ra.

## 6. SplittableRandom: tạo các luồng ngẫu nhiên độc lập cho tính toán song song

java.util.SplittableRandom được thiết kế cho các tình huống cần nhiều generator con, đặc biệt trong xử lý song song.

Khác với Random, SplittableRandom **không thread-safe**. Không nên chia sẻ cùng một instance cho nhiều thread cùng lúc.

### 6.1. Tạo generator bằng seed cố định

```java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom random = new SplittableRandom(12345L);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

Với cùng seed và cùng thứ tự gọi, chương trình có thể tái hiện chuỗi kết quả theo hợp đồng của SplittableRandom.

### 6.2. Tách generator con bằng split()

```java
SplittableRandom root = new SplittableRandom(12345L);

SplittableRandom workerA = root.split();
SplittableRandom workerB = root.split();

int sampleA = workerA.nextInt(100);
int sampleB = workerB.nextInt(100);
```

split() trả về một generator mới được tách từ trạng thái của generator cha. Các generator con được thiết kế để tạo chuỗi độc lập về mặt thống kê phù hợp cho các tác vụ khác nhau.

Để tái hiện, cần giữ:

- Seed của generator gốc.
- Số lần gọi split().
- Thứ tự gọi split().
- Generator con nào được gán cho tác vụ nào.
- Thứ tự gọi trong từng generator con.

### 6.3. Mô hình đúng cho tác vụ song song có thể phát lại

Tách generator con **tuần tự trước**, rồi mới giao từng generator cho tác vụ:

```java
import java.util.SplittableRandom;
import java.util.concurrent.CompletableFuture;

public class ParallelReplayDemo {

    static long simulate(SplittableRandom random) {
        long total = 0;
        for (int i = 0; i < 1_000; i++) {
            total += random.nextInt(1_000);
        }
        return total;
    }

    public static void main(String[] args) {
        SplittableRandom root = new SplittableRandom(987654321L);

        // Tách theo thứ tự xác định trước khi submit task.
        SplittableRandom randomA = root.split();
        SplittableRandom randomB = root.split();

        CompletableFuture<Long> taskA =
                CompletableFuture.supplyAsync(() -> simulate(randomA));
        CompletableFuture<Long> taskB =
                CompletableFuture.supplyAsync(() -> simulate(randomB));

        // Đọc kết quả theo danh tính task, không theo thứ tự hoàn thành.
        long resultA = taskA.join();
        long resultB = taskB.join();

        System.out.println("A=" + resultA);
        System.out.println("B=" + resultB);
    }
}
```

Hai tác vụ chạy song song nhưng mỗi tác vụ sở hữu một generator riêng. Nếu seed gốc, thứ tự split, mã trong từng tác vụ và dữ liệu đầu vào không đổi, kết quả gắn với task A và task B có thể được tái hiện. **Thời điểm task A hay B hoàn tất không phải yếu tố quyết định chuỗi số**, miễn là chúng không chia sẻ generator và không có trạng thái dùng chung khác ảnh hưởng kết quả.

Không nên để mỗi thread tự gọi root.split() trên cùng một SplittableRandom. Lớp này không thread-safe; thứ tự tách phụ thuộc lịch thực thi và có thể tạo race condition.

### 6.4. Tách theo cấu trúc công việc

Với thí nghiệm phân rã thành các nhóm, hãy dùng quy tắc cố định:

```text
master seed
    |
    +-- split theo nhóm A
    |       +-- các lần gọi của A
    |
    +-- split theo nhóm B
            +-- các lần gọi của B
```

Tránh gán generator theo thread ID hoặc thứ tự thread được scheduler tạo ra. Một tác vụ có thể chạy trên thread khác giữa hai lần chạy; danh tính của dữ liệu thí nghiệm phải gắn với **task/partition ổn định**, không phải thread tạm thời.

## 7. API RandomGenerator trong Java 17

Java 17 bổ sung package java.util.random và giao diện RandomGenerator (JEP 356). API này tạo một cách dùng chung cho nhiều thuật toán PRNG thay vì phải phụ thuộc trực tiếp vào từng lớp cụ thể.

Các lớp quen thuộc như Random, SplittableRandom và ThreadLocalRandom cũng tích hợp với hệ sinh thái RandomGenerator.

### 7.1. Sử dụng giao diện chung

```java
import java.util.random.RandomGenerator;

public class GeneratorInterfaceDemo {
    static void printSamples(RandomGenerator random) {
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble());
        System.out.println(random.nextBoolean());
    }
}
```

Phương thức printSamples không phụ thuộc vào một lớp PRNG cụ thể. Bên gọi có thể truyền Random, SplittableRandom hoặc một implementation khác phù hợp.

Tuy nhiên, nếu mục tiêu là tái hiện, chỉ khai báo kiểu RandomGenerator là chưa đủ. Phải ghi rõ **implementation/algorithm thực tế** đã được truyền vào.

### 7.2. Chọn thuật toán bằng RandomGeneratorFactory

Java 17 cung cấp RandomGeneratorFactory để tra cứu và tạo generator theo tên thuật toán:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryDemo {
    public static void main(String[] args) {
        long seed = 20261115L;

        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(seed);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

Ở đây:

- Tên L64X128MixRandom xác định thuật toán được chọn trong runtime.
- factory.create(seed) tạo một generator với seed cụ thể.
- Kiểu tham chiếu RandomGenerator giúp mã dùng các phương thức sinh số chung.

Các thuật toán LXM là một phần của các generator được cung cấp trong Java 17. Có thể liệt kê các tên mà runtime hiện tại cung cấp:

```java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
```

### 7.3. Vì sao phải ghi cả tên thuật toán?

Metadata:

```text
seed = 12345
algorithm = L64X128MixRandom
```

chứa nhiều thông tin hơn:

```text
seed = 12345
```

Các implementation RandomGenerator khác nhau có thuật toán và trạng thái khác nhau. Ngoài ra, tài liệu API của RandomGeneratorFactory cho phép các implementation được điều chỉnh giữa các bản phát hành Java; tên thuật toán được giữ ổn định nhưng không nên mặc định mọi chi tiết chuỗi bit của mọi implementation sẽ bất biến qua mọi phiên bản runtime.

Nếu cần tái hiện chính xác lâu dài:

- Chọn một thuật toán cụ thể, không dùng mặc định ngầm.
- Ghi tên thuật toán và phiên bản Java/vendor runtime.
- Giữ phiên bản runtime hoặc bộ sinh đã được xác nhận trong quy trình thí nghiệm.
- Nếu yêu cầu portable lâu dài ở cấp API Java, java.util.Random có lợi thế vì thuật toán của lớp này được đặc tả cụ thể.
- Nếu cần thuật toán khác, đọc hợp đồng của implementation và chủ động kiểm thử giữa các phiên bản runtime mà dự án hỗ trợ.

## 8. Chọn generator theo mục đích

| API | Đặc điểm | Khi nên dùng |
|---|---|---|
| java.util.Random | LCG 48-bit, thread-safe, thuật toán được đặc tả lâu dài | Thí nghiệm đơn giản cần tái hiện dễ dàng và chuỗi ổn định theo hợp đồng Java |
| java.util.SplittableRandom | Hỗ trợ split, không thread-safe | Tách luồng PRNG cho các tác vụ độc lập, đặc biệt trong tính toán song song có cấu trúc |
| java.util.random.RandomGenerator | Giao diện chung cho nhiều generator | Viết API nhận generator từ bên gọi, tách thuật toán khỏi logic |
| RandomGeneratorFactory | Tra cứu/tạo generator theo tên thuật toán | Chọn thuật toán rõ ràng và lưu tên generator trong metadata |
| ThreadLocalRandom | Generator gắn với thread, tối ưu cho truy cập đồng thời; không cho người dùng đặt seed | Tác vụ đa luồng thông thường không cần tái hiện chuỗi |
| SecureRandom | PRNG phục vụ yêu cầu bảo mật, có nguồn entropy và cơ chế seed riêng | Token, nonce, khóa hoặc dữ liệu bảo mật; không dùng để phát lại thí nghiệm |
| Math.random() | API đơn giản dùng nguồn pseudo-random nội bộ, không cho truyền seed trực tiếp | Ví dụ nhỏ không cần quản lý generator; không phù hợp khi cần tái hiện có kiểm soát |

Không có generator “tốt nhất” cho mọi tình huống. Hãy bắt đầu từ yêu cầu:

- Cần tái hiện portable và đơn giản? Cân nhắc Random.
- Cần nhiều luồng độc lập cho simulation? Cân nhắc SplittableRandom.
- Cần chọn thuật toán hiện đại theo tên? Cân nhắc RandomGeneratorFactory.
- Cần bảo mật? Dùng SecureRandom, không dùng seed cố định.
- Cần throughput nhiều thread và không quan tâm phát lại? ThreadLocalRandom có thể phù hợp.

## 9. Những API dễ gây hiểu nhầm khi cần tái hiện

### 9.1. Math.random()

Math.random() trả về double trong khoảng [0.0, 1.0). Nó tiện cho ví dụ nhỏ:

```java
double probability = Math.random();
```

Nhưng không có tham số seed hoặc đối tượng generator để ứng dụng điều khiển trạng thái trực tiếp. Nếu cần phát lại:

```java
Random random = new Random(12345L);
double probability = random.nextDouble();
```

### 9.2. ThreadLocalRandom

ThreadLocalRandom.current() lấy generator gắn với thread hiện tại. API này không cung cấp cách đặt seed tùy ý như new Random(seed); gọi setSeed trên ThreadLocalRandom sẽ ném UnsupportedOperationException.

Điều này giúp tránh tranh chấp khi nhiều thread sinh số, nhưng khó kiểm soát chuỗi cho thí nghiệm tái hiện. Cũng không nên nghĩ rằng seed gắn với thread sẽ gắn với một task logic: cùng task có thể chạy trên thread khác ở lần thực thi khác.

### 9.3. SecureRandom

SecureRandom được thiết kế cho mục đích bảo mật. Nó có thể lấy entropy từ hệ thống và có thể trộn seed bổ sung vào trạng thái. Việc gọi setSeed không biến nó thành một PRNG mô phỏng có chuỗi portable, dễ phát lại theo cùng hợp đồng như Random.

Không nên dùng SecureRandom cho mô phỏng cần tái hiện; cũng không nên dùng Random, SplittableRandom hay ThreadLocalRandom để sinh mật khẩu, token bảo mật hoặc khóa mật mã.

### 9.4. Constructor không tham số

```java
new Random()
new SplittableRandom()
```

Hai dạng trên không thể hiện seed cố định trong mã. Nếu dùng chúng, hãy ghi lại seed/trạng thái theo một cơ chế có thể kiểm soát; tốt hơn là truyền seed được lưu trong cấu hình cho thí nghiệm.

## 10. nextGaussian() và trạng thái phụ thuộc phương thức

Không phải mọi phương thức sinh số đều chỉ tiêu thụ một bước trạng thái theo cách dễ đoán.

Ví dụ Random.nextGaussian() có cơ chế tạo giá trị phân phối chuẩn và lưu một giá trị để dùng ở lần gọi tiếp theo. Điều đó có nghĩa thứ tự gọi các phương thức khác nhau có thể ảnh hưởng cách các giá trị được tạo và tiêu thụ.

```java
Random random = new Random(42L);

double firstGaussian = random.nextGaussian();
int nextInteger = random.nextInt(100);
```

Khi thay đổi chuỗi lời gọi, cần ghi rõ cả các phương thức như:

- nextInt(bound)
- nextLong()
- nextDouble()
- nextBoolean()
- nextGaussian()
- nextBytes(byte[])

Một phương thức có thể dùng một hoặc nhiều phần của trạng thái nội bộ; một số phương thức còn có cache. Vì vậy, không nên chỉ đếm “số lần gọi random” chung chung. Hãy ghi **tên phương thức, tham số và thứ tự**.

## 11. Tái hiện khi có điều kiện rẽ nhánh

Giả sử:

```java
if (random.nextDouble() < 0.5) {
    int bonus = random.nextInt(100);
}

int result = random.nextInt(100);
```

Nếu nhánh điều kiện khác nhau giữa hai lần chạy, số lần gọi generator khác nhau. Khi đó result có thể lấy một phần tử khác trong chuỗi.

Trong một thí nghiệm cần so sánh hai thuật toán, hãy cân nhắc:

1. Dùng cùng một seed ban đầu cho mỗi lần chạy.
2. Tạo dữ liệu đầu vào ngẫu nhiên trước rồi lưu lại, sau đó chạy các thuật toán trên cùng dataset.
3. Hoặc tách generator riêng cho từng nguồn dữ liệu/nhánh để một thay đổi không làm lệch các phần độc lập.
4. Ghi rõ nếu số lần gọi phụ thuộc nhánh điều kiện.

Ví dụ tạo dataset một lần:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

static List<Integer> createDataset(long seed, int size) {
    Random random = new Random(seed);
    List<Integer> values = new ArrayList<>();
    for (int i = 0; i < size; i++) {
        values.add(random.nextInt(1_000));
    }
    return List.copyOf(values);
}
```

Sau đó, cả thuật toán A và B đều nhận cùng một danh sách. Điều này giúp tách sự khác nhau do **dữ liệu đầu vào** khỏi sự khác nhau do **logic thuật toán**.

## 12. Seed, dữ liệu và kết quả thí nghiệm: lưu cái gì?

Để người khác có thể phát lại, nên lưu một manifest đơn giản:

```yaml
experiment:
  id: "queue-simulation-001"
  version: "v2"
  seed: 20261115
  generator:
    class: "java.util.Random"
    algorithm: "48-bit LCG specified by java.util.Random"
  runtime:
    java: "17"
    vendor: "record actual runtime vendor"
  input:
    dataset: "queue-input-v4"
    checksum: "record actual checksum"
  execution:
    parallelism: 1
    callOrder:
      - "nextInt(11): requestCount"
      - "nextInt(451): delay"
      - "nextDouble(): failureDecision"
```

Đây là cấu trúc minh họa, không phải file cấu hình bắt buộc của Java. Các giá trị vendor/checksum cần được thay bằng dữ liệu thực.

Nên ghi:

- Seed dạng số chính xác (và kiểu, ví dụ long).
- Tên lớp/thuật toán generator.
- Java runtime/version/vendor nếu cần so sánh qua môi trường.
- Thứ tự gọi và tham số, kể cả những nhánh có thể gọi thêm.
- Dataset hoặc cách sinh dataset, kèm checksum nếu dữ liệu lớn.
- Phiên bản mã nguồn/commit của thí nghiệm.
- Cấu hình song song và quy tắc split/seed con.
- Locale, timezone và rounding nếu có ảnh hưởng đến đầu ra.

### 12.1. Có nên chỉ lưu kết quả số ngẫu nhiên?

Lưu các số đã sinh có thể hữu ích để phát lại đúng dataset mà không phụ thuộc PRNG. Nhưng nó không thay thế hoàn toàn metadata:

- Nếu muốn kiểm tra generator hoặc thuật toán sinh dữ liệu, vẫn cần seed và tên generator.
- Nếu muốn phát lại lỗi, cần biết số nào tương ứng với bước nào.
- Nếu dữ liệu lớn, có thể lưu dataset thành artifact riêng và ghi checksum.

Trong thí nghiệm quan trọng, cách đáng tin cậy là lưu cả **metadata tái hiện** và **đầu vào thực tế** được dùng cho lần chạy.

## 13. Các nguyên tắc thiết kế cho thí nghiệm tái hiện

### 13.1. Đưa seed thành tham số đầu vào

Tránh ẩn seed bên trong constructor không tham số. Cho phép chạy lại với cùng seed:

```java
static void run(long seed) {
    Random random = new Random(seed);
    // Thực hiện thí nghiệm
}
```

Seed nên được ghi trong log đầu thí nghiệm, trước khi có lỗi có thể xảy ra.

### 13.2. Một nguồn ngẫu nhiên cho một mục đích

Tách generator theo chức năng (tạo dữ liệu, chọn nhánh lỗi, thêm nhiễu) để sửa một thành phần không làm dịch toàn bộ chuỗi của thành phần khác. Quy tắc tạo seed con phải ổn định và được lưu.

### 13.3. Không chia sẻ generator mutable tùy tiện giữa thread

Random có thread-safety, nhưng chia sẻ một generator giữa nhiều thread vẫn khiến thứ tự thread nhận số phụ thuộc lịch chạy. SplittableRandom không thread-safe, nên tạo instance riêng cho mỗi task.

### 13.4. Phân biệt thứ tự thực thi và thứ tự thu kết quả

Nếu tác vụ chạy song song, thời điểm hoàn thành có thể thay đổi. Hãy lưu kết quả theo task ID/partition ID và ghép theo thứ tự logic cố định, không ghép theo thứ tự callback hoàn tất.

### 13.5. Đừng thay thuật toán mà không đổi metadata

Chuyển từ Random sang L64X128MixRandom dù vẫn giữ seed là thay đổi thuật toán. Hãy ghi phiên bản thí nghiệm mới hoặc trường generator mới để không nhầm hai lần chạy.

### 13.6. Seed cố định không phải bảo mật

Nếu seed và thuật toán đã biết, chuỗi PRNG có thể dự đoán. Không dùng seed cố định để tạo session token, mật khẩu, mã xác thực hoặc khóa.

## 14. Bài tập thực hành

### Bài 1 — Tạo hai lần chạy giống nhau

Viết phương thức:

```java
static int[] generate(long seed, int count) {
    // Trả về count số nguyên trong [0, 99].
}
```

Yêu cầu:

- Dùng Random khởi tạo bằng seed truyền vào.
- Gọi nextInt(100) đúng một lần cho mỗi phần tử.
- Tạo hai mảng với cùng seed và so sánh từng phần tử.

**Gợi ý lời giải:**

```java
import java.util.Random;
import java.util.Arrays;

static int[] generate(long seed, int count) {
    Random random = new Random(seed);
    int[] values = new int[count];
    for (int i = 0; i < count; i++) {
        values[i] = random.nextInt(100);
    }
    return values;
}

int[] first = generate(2026L, 10);
int[] second = generate(2026L, 10);
System.out.println(Arrays.equals(first, second)); // true
```

### Bài 2 — Chứng minh thứ tự gọi có ảnh hưởng

Tạo hai generator cùng seed. Ở generator thứ nhất gọi nextInt(100) hai lần. Ở generator thứ hai gọi nextInt(100), sau đó gọi thêm nextDouble(), rồi mới gọi nextInt(100).

So sánh số nguyên thứ hai của hai generator. Giải thích vì sao kết quả khác nhau trong trường hợp thông thường.

### Bài 3 — Tách luồng theo mục đích

Viết mô phỏng có hai nguồn:

- Generator A tạo số lượng người dùng.
- Generator B tạo thời gian xử lý.

Thêm một lời gọi mới vào generator A và chứng minh chuỗi của B không đổi khi dùng seed độc lập.

### Bài 4 — Tạo generator theo thuật toán trong Java 17

Dùng RandomGeneratorFactory.of("L64X128MixRandom") để tạo generator với seed cố định. In tên thuật toán từ factory và tạo năm số nguyên có giới hạn. Chạy lại chương trình để quan sát kết quả.

Sau đó thay tên thuật toán bằng một tên khác được runtime liệt kê. Giải thích vì sao cùng seed không bắt buộc tạo cùng chuỗi khi đổi thuật toán.

### Bài 5 — Tái hiện tác vụ song song

Tạo một SplittableRandom gốc, gọi split() tuần tự hai lần để tạo generator cho task A và B. Chạy hai task song song, lưu kết quả theo task ID. Lặp lại cùng seed và cấu trúc split, so sánh kết quả từng task.

Giải thích vì sao chia sẻ một SplittableRandom gốc giữa hai thread để gọi split() đồng thời không phải thiết kế an toàn.

### Bài 6 — Phát hiện generator không phù hợp

Trong các mục tiêu sau, chọn API phù hợp và giải thích:

1. Mô phỏng queue có thể phát lại.
2. Sinh token reset mật khẩu.
3. Chạy nhiều task simulation độc lập trên nhiều thread.
4. Sinh số ngẫu nhiên nhanh cho tác vụ không cần seed tái hiện.

**Định hướng:** Random hoặc generator có thuật toán được chọn rõ cho mô phỏng; SecureRandom cho token; SplittableRandom với split có kiểm soát cho task độc lập; ThreadLocalRandom cho truy cập đa luồng thông thường không cần phát lại.

## 15. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Cùng seed thì mọi PRNG tạo cùng chuỗi | Chuỗi phụ thuộc cả thuật toán và seed |
| Lưu seed là đủ để phát lại | Cần cả thứ tự, loại phương thức, tham số, dữ liệu và cấu hình thực thi |
| Thêm một lệnh random để debug không ảnh hưởng kết quả | Nó có thể làm dịch trạng thái và thay đổi mọi kết quả phía sau |
| Random thread-safe nên chia sẻ giữa thread sẽ tái hiện | An toàn dữ liệu không đồng nghĩa thứ tự mỗi task nhận số là cố định |
| SplittableRandom có thể dùng chung giữa thread | Lớp này không thread-safe; hãy tách generator riêng |
| ThreadLocalRandom có thể đặt seed như Random | API không cho điều khiển seed tùy ý; setSeed không hỗ trợ |
| SecureRandom là PRNG tốt nhất cho thí nghiệm | Nó dành cho bảo mật, không phải phát lại chuỗi mô phỏng |
| Math.random() cho phép tái hiện nếu biết thời gian chạy | API không cho truyền seed; hãy quản lý generator tường minh |
| Seed cố định tạo tính ngẫu nhiên bảo mật | Seed và thuật toán biết trước khiến chuỗi có thể dự đoán |
| Parallel task hoàn tất khác thứ tự thì kết quả số nhất thiết khác | Nếu mỗi task có generator riêng và kết quả gắn với task ID, thứ tự hoàn tất không nhất thiết ảnh hưởng chuỗi |

## 16. Tài liệu chính thức của Java 17

- [Java SE 17 API — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): thuật toán LCG, seed và hợp đồng chuỗi số có thể tái hiện.
- [Java SE 17 API — SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): seed, split và giới hạn thread-safety.
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): giao diện chung của các generator trong Java 17.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): chọn và tạo generator theo tên thuật toán.
- [Java SE 17 API — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator gắn với thread và hạn chế đặt seed.
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generator cho mục đích bảo mật.
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): bổ sung RandomGenerator API và các thuật toán mới từ Java 17.

**Ghi nhớ:** Để tái hiện một thí nghiệm, phải lưu và giữ ổn định **thuật toán + seed + thứ tự gọi + tham số + dữ liệu đầu vào**. Trong xử lý song song, gán generator riêng theo tác vụ bằng quy tắc split/seed ổn định. Seed cố định giúp tái hiện chuỗi giả ngẫu nhiên; nó không tạo ra bảo mật và cũng không tự bảo đảm toàn bộ ứng dụng tái hiện nếu logic, thứ tự thực thi hoặc môi trường thay đổi.
