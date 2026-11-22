# Phân biệt bộ sinh `splittable`, `jumpable` và `leapable` trong Java 17

**Chủ đề:** Java 17  
**Chương:** Sinh số giả ngẫu nhiên  
**Bài học:** Phân biệt bộ sinh splittable, jumpable và leapable

Khi nhiều tác vụ hoặc nhiều luồng cùng cần sinh số giả ngẫu nhiên, việc tạo một bộ sinh riêng cho từng tác vụ không chỉ là chuyện gọi `new Random()` nhiều lần. Nếu các bộ sinh dùng cùng thuật toán và được khởi tạo thiếu cẩn thận, các chuỗi kết quả có thể tương quan hoặc trùng vùng trạng thái. Java 17 cung cấp các interface chuyên biệt trong package `java.util.random` để tạo những bộ sinh có đặc tính thống kê tương tự nhưng đi theo các phần khác nhau của chu trình trạng thái.

Ba cách tổ chức thường gặp là:

- **Splittable:** gọi `split()` để tạo một bộ sinh con từ bộ sinh hiện tại. Cả bộ sinh cha và bộ sinh con tiếp tục có thể sinh số và có thể được chia tiếp.
- **Jumpable:** gọi `jump()` để đưa trạng thái của chính bộ sinh tiến nhanh một khoảng cố định rất lớn trên chu trình. Có thể tạo một dãy bộ sinh bằng `jumps()`.
- **Leapable:** mở rộng `JumpableGenerator`, bổ sung `leap()` để tiến một khoảng còn lớn hơn. Có thể dùng `leaps()` tạo các luồng bộ sinh ở những vùng xa nhau, rồi dùng `jump()` để chia nhỏ tiếp.

Các interface này được đưa vào API chuẩn trong Java 17 cùng JEP 356. Chúng giải quyết bài toán **phân phối trạng thái PRNG cho tính toán song song**; không phải các chế độ mã hóa, không bảo đảm tuyệt đối mọi giá trị sinh ra đều khác nhau, và không thay thế `SecureRandom` trong ứng dụng bảo mật.

## 1. Bối cảnh: một PRNG có trạng thái và chu kỳ

PRNG là bộ sinh số giả ngẫu nhiên (*pseudorandom number generator*). Nó sử dụng thuật toán xác định để biến trạng thái hiện tại thành trạng thái tiếp theo và tạo ra giá trị đầu ra.

Một cách hình dung đơn giản:

```text
seed / trạng thái ban đầu
          |
          v
       PRNG
          |
          v
     giá trị ngẫu nhiên
          |
          v
   trạng thái kế tiếp
          |
          +------> giá trị tiếp theo ...
```

Vì trạng thái có số lượng hữu hạn, một PRNG tất định cuối cùng sẽ quay lại trạng thái đã gặp. Số bước trước khi chuỗi lặp lại được gọi là **period** (chu kỳ).

Khi chỉ có một luồng thực thi, có thể dùng một đối tượng generator và lần lượt gọi `nextInt()`, `nextLong()` hoặc `nextDouble()`. Khi có nhiều worker, ta muốn mỗi worker sử dụng một chuỗi riêng có đặc tính thống kê tương đương, thay vì cùng thao tác trên một trạng thái dùng chung.

### 1.1. Vì sao không chia sẻ một generator mutable?

Ví dụ:

```java
RandomGenerator random = RandomGenerator.of("L64X128MixRandom");

// Không nên để nhiều thread cùng gọi nextLong() trên một instance
// nếu đang thiết kế luồng PRNG riêng cho từng worker.
```

Phần lớn implementation của `RandomGenerator` không được bảo đảm thread-safe. Việc chia sẻ có thể dẫn đến tranh chấp trạng thái, kết quả phụ thuộc lịch thực thi và làm mất khả năng kiểm soát chuỗi của từng worker.

Mô hình tốt hơn:

```text
                 Generator gốc
                       |
          +------------+------------+
          |            |            |
       Worker 1     Worker 2     Worker 3
       Generator    Generator    Generator
       riêng        riêng        riêng
```

Các interface `SplittableGenerator`, `JumpableGenerator` và `LeapableGenerator` cung cấp những chiến lược khác nhau để tạo ra các generator riêng này.

### 1.2. “Độc lập thống kê” không có nghĩa là không bao giờ trùng số

Mục tiêu là các chuỗi có đặc tính gần như độc lập và phân phối phù hợp với thuật toán. Hai worker vẫn có thể sinh ra cùng một số, ví dụ cả hai cùng sinh `42`. Điều đó không tự động chứng minh hai chuỗi bị trùng hoặc có lỗi.

Cần phân biệt:

- **Trùng giá trị đầu ra:** Hoàn toàn có thể xảy ra trong các chuỗi ngẫu nhiên hợp lệ.
- **Trùng hoặc chồng lấn vùng trạng thái:** Có thể làm các chuỗi phụ thuộc nhau; đây là điều thiết kế split/jump/leap muốn hạn chế.
- **Độc lập thống kê:** Là mục tiêu chất lượng của các chuỗi, thường chỉ đạt được theo mức xấp xỉ của thuật toán cụ thể.

Không nên diễn giải tài liệu API thành cam kết rằng mọi giá trị ở mọi worker đều duy nhất.

## 2. Ba interface nằm ở đâu trong API Java 17?

Các interface là interface lồng trong `java.util.random.RandomGenerator`:

```java
RandomGenerator.SplittableGenerator
RandomGenerator.JumpableGenerator
RandomGenerator.LeapableGenerator
```

Chúng cùng mở rộng `RandomGenerator.StreamableGenerator`, vì vậy đều có thể tạo stream các generator theo cách thích hợp. Quan hệ kế thừa quan trọng:

```text
                    RandomGenerator
                           |
                  StreamableGenerator
                    /      |       \
                   /       |        \
          Splittable   Jumpable   (các interface streamable)
                         |
                      Leapable
```

`LeapableGenerator` **extends `JumpableGenerator`**. Vì vậy, một bộ sinh leapable cũng có thể jump. Một bộ sinh jumpable thông thường không nhất thiết có thể leap.

`SplittableGenerator` là một nhánh riêng; nó không kế thừa `JumpableGenerator` hay `LeapableGenerator`.

| Interface | Khả năng chính | Cách tạo generator khác |
|---|---|---|
| `SplittableGenerator` | Chia generator thành nhánh con có thể tiếp tục chia | `split()`, `splits()` |
| `JumpableGenerator` | Tiến trạng thái một khoảng cố định lớn trong chu trình | `jump()`, `jumps()` |
| `LeapableGenerator` | Jump và tiến xa hơn bằng leap | `jump()`, `leap()`, `jumps()`, `leaps()` |

Java 17 còn có `ArbitrarilyJumpableGenerator`, một interface chuyên biệt cho thuật toán có thể nhảy theo khoảng do người dùng chỉ định. Bài này tập trung vào ba chiến lược split, jump và leap.

## 3. Splittable: tạo bộ sinh con bằng `split()`

### 3.1. Ý tưởng

Một `SplittableGenerator` có thể tạo ra một generator con từ trạng thái hiện tại:

```text
             Generator cha
                   |
                split()
                /     \
               /       \
      Generator cha   Generator con
         tiếp tục       mới tạo
            |              |
         sinh số         sinh số
            |              |
         split()         split()
          /  \            /  \
        ...  ...        ...  ...
```

Cả hai đối tượng đều tiếp tục thực hiện vai trò generator. Generator cha vẫn thuộc luồng đã tạo nó; generator con được chuyển cho tác vụ mới. Mỗi nhánh có thể tiếp tục split đệ quy khi cần.

API chính:

```java
SplittableGenerator child = parent.split();
```

Phương thức `split()` trả về một `SplittableGenerator` mới. Generator hiện tại cũng có thể thay đổi trạng thái trong quá trình tạo generator con.

### 3.2. Ví dụ cơ bản

```java
import java.util.random.RandomGenerator.SplittableGenerator;

public class SplitBasic {
    public static void main(String[] args) {
        SplittableGenerator parent =
                SplittableGenerator.of("L64X128MixRandom");

        SplittableGenerator child = parent.split();

        System.out.println("Parent: " + parent.nextLong());
        System.out.println("Child:  " + child.nextLong());
    }
}
```

`L64X128MixRandom` là một thuật toán LXM trong JDK 17 có hỗ trợ `SplittableGenerator`. `parent` và `child` là hai đối tượng riêng biệt; có thể dùng một cho tác vụ hiện tại và chuyển đối tượng còn lại cho tác vụ được fork.

### 3.3. Dùng `splits()` tạo nhiều generator

Thay vì gọi `split()` thủ công nhiều lần, có thể tạo stream:

```java
import java.util.List;
import java.util.random.RandomGenerator.SplittableGenerator;

public class SplitStream {
    public static void main(String[] args) {
        SplittableGenerator root =
                SplittableGenerator.of("L64X128MixRandom");

        List<SplittableGenerator> workers =
                root.splits(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

`splits(4)` tạo stream gồm bốn generator con. `toList()` có từ Java 16 nên dùng được trong Java 17.

`splits()` không tham số tạo stream gần như không giới hạn; trong ứng dụng, nên giới hạn số lượng bằng `splits(count)` hoặc `limit(count)` để tránh tạo nhiều generator hơn nhu cầu.

### 3.4. Khi nào nên chọn splittable?

Splittable thường phù hợp khi:

- Tác vụ mới có thể được tạo động trong lúc chương trình đang chạy.
- Một worker có thể fork thành nhiều worker con.
- Cấu trúc tính toán là cây hoặc đệ quy.
- Số lượng tác vụ chưa cố định ngay từ đầu.
- Muốn một generator thuộc riêng từng nhánh xử lý.

Ví dụ, một thuật toán chia nhỏ dữ liệu thành các vùng con có thể giữ một generator cho mỗi nhánh. Khi nhánh tiếp tục chia, nó gọi `split()` trên generator của chính nhánh đó rồi chuyển generator mới cho công việc con.

### 3.5. Quy tắc sở hữu generator cha

Một generator splittable cũng là đối tượng mutable. Nếu nhiều thread cùng gọi `split()` trên một generator cha duy nhất, ta đã quay lại bài toán chia sẻ trạng thái.

Mô hình phù hợp:

1. Thread hiện tại sở hữu generator cha.
2. Khi cần tạo tác vụ con, thread đó gọi `split()`.
3. Generator mới được chuyển cho worker con.
4. Worker con chỉ sử dụng generator của mình và có thể tiếp tục split nếu cần.

Không dùng một instance chung cho nhiều worker rồi gọi `split()` đồng thời nếu implementation không bảo đảm thread safety.

## 4. Jumpable: tiến nhanh trong chu trình trạng thái

### 4.1. Ý tưởng

Với `JumpableGenerator`, thay vì tạo nhánh theo kiểu split, generator có thể **nhảy về phía trước một khoảng cố định lớn** trong chu trình trạng thái.

Ví dụ minh họa:

```text
Một chu trình trạng thái dài:

... A ---------------- B ---------------- C ---------------- D ...

     khoảng jump         khoảng jump         khoảng jump
         |                   |                   |
       Worker 1            Worker 2            Worker 3
```

`jump()` thay đổi trạng thái của **chính generator đang gọi**. Nó không trả về một generator con.

```java
jumpable.jump();
```

Khoảng nhảy là đặc tính của thuật toán cụ thể. Tài liệu JDK mô tả jump thường có độ lớn cỡ `2^64` bước hoặc hơn; không được giả định mọi implementation dùng chính xác một khoảng giống nhau.

### 4.2. Các phương thức quan trọng

| Phương thức | Ý nghĩa |
|---|---|
| `copy()` | Tạo generator mới có trạng thái nội bộ giống hệt trạng thái hiện tại |
| `jump()` | Tiến trạng thái của generator hiện tại một khoảng cố định |
| `copyAndJump()` | Copy trạng thái hiện tại, jump generator gốc, rồi trả về bản copy |
| `jumpDistance()` | Cho biết khoảng cách jump của implementation |
| `jumps()` | Tạo stream các generator từ những bản copy và lần lượt jump trạng thái gốc |
| `jumps(long count)` | Tạo stream có số lượng generator được chỉ định |

Điểm dễ nhầm: `copy()` tạo bản sao trạng thái; nếu hai bản sao tiếp tục nhận cùng chuỗi thao tác, chúng có thể sinh cùng chuỗi kết quả. `jump()` là thao tác giúp dịch chuyển generator gốc đến vùng khác của chu trình.

### 4.3. Ví dụ dùng `jump()`

```java
import java.util.random.RandomGenerator.JumpableGenerator;

public class JumpBasic {
    public static void main(String[] args) {
        JumpableGenerator random =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        long first = random.nextLong();

        random.jump();

        long afterJump = random.nextLong();

        System.out.println("Before jump: " + first);
        System.out.println("After jump:  " + afterJump);
        System.out.println("Jump distance: " + random.jumpDistance());
    }
}
```

`jump()` không phải lệnh sinh ra một số ngẫu nhiên mới. Nó chuyển trạng thái PRNG đi xa trong chu trình; lời gọi `nextLong()` tiếp theo mới lấy một giá trị từ trạng thái sau khi nhảy.

### 4.4. Dùng `jumps()` tạo generator cho nhiều worker

```java
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGenerator.JumpableGenerator;

public class JumpStream {
    public static void main(String[] args) {
        JumpableGenerator root =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        List<RandomGenerator> workers =
                root.jumps(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

Có một chi tiết API rất quan trọng: `jumps()` trả về `Stream<RandomGenerator>`, không phải `Stream<JumpableGenerator>`. Các generator trong stream cần được xem theo kiểu `RandomGenerator`; không nên ép kiểu ngược rồi giả định tất cả đều có thể gọi `jump()`.

Default implementation tạo stream bằng cách copy trạng thái hiện tại rồi jump generator gốc lặp lại. Vì vậy, đây là cách tạo các generator ở các vị trí cách xa nhau trong chu trình.

### 4.5. Khi nào nên chọn jumpable?

Jumpable phù hợp khi:

- Số lượng worker hoặc nhánh tính toán được biết trước.
- Muốn cấp các vùng trạng thái cách xa nhau trong một chu trình dài.
- Có thể tạo một stream generator theo lô trước khi bắt đầu chạy song song.
- Mỗi worker sẽ sử dụng một lượng giá trị được giới hạn theo giả định của thuật toán.

Tài liệu JDK mô tả chiến lược thường dùng là tạo một `JumpableGenerator` gốc, gọi `jumps()` để tạo stream generator, sau đó cấp mỗi generator cho một thread.

### 4.6. Không jump tùy tiện trên generator đã được tạo từ stream

Javadoc của `JumpableGenerator` lưu ý rằng không nên mặc định gọi `jump()` trên một generator vốn đã được tạo ra bởi `jumps()`. Việc đó có thể tạo ra trạng thái trùng với generator khác đã được tạo trong stream.

Hãy để generator gốc quản lý việc cấp phát vùng trạng thái bằng `jumps()`. Mỗi generator nhận được nên được giao cho một worker và dùng như một generator thông thường, trừ khi hợp đồng của implementation nói rõ cách tiếp tục phân nhánh.

## 5. Leapable: nhảy xa hơn và phân cấp hai tầng

### 5.1. Ý tưởng

`LeapableGenerator` kế thừa `JumpableGenerator`, do đó có cả khả năng jump lẫn leap.

- `jump()` tiến trạng thái một khoảng lớn cố định.
- `leap()` tiến trạng thái một khoảng còn lớn hơn.

Tài liệu JDK mô tả jump thường có khoảng cách cỡ `2^64` bước hoặc hơn, còn leap thường cỡ `2^96` bước hoặc hơn; hướng dẫn API cũng mô tả leap điển hình cỡ `2^128`. Đây là **mức minh họa**, khoảng cách thật phụ thuộc thuật toán và có thể đọc qua `jumpDistance()` và `leapDistance()`.

Sơ đồ phân cấp:

```text
                   Generator gốc
                         |
                       leap()
                /        |        \
               /         |         \
        Generator A  Generator B  Generator C
           (jumpable)   (jumpable)   (jumpable)
              |            |            |
            jump()       jump()       jump()
           /   \         /   \        /   \
          ...  ...      ...  ...     ...  ...
```

Đây là điểm mạnh của leapable: chia các vùng rất xa cho nhóm worker lớn, sau đó dùng jump để chia các nhánh con bên trong từng vùng.

### 5.2. Các phương thức quan trọng

| Phương thức | Ý nghĩa |
|---|---|
| `jump()` | Khả năng được kế thừa từ `JumpableGenerator` |
| `leap()` | Tiến trạng thái hiện tại một khoảng lớn hơn jump |
| `copy()` | Tạo bản sao trạng thái |
| `copyAndLeap()` | Copy trạng thái, leap generator gốc, trả về bản copy |
| `jumpDistance()` | Khoảng cách jump |
| `leapDistance()` | Khoảng cách leap |
| `jumps()` | Tạo stream generator bằng các bước jump |
| `leaps()` | Tạo stream generator bằng các bước leap |

Một điểm API khác biệt: `leaps()` trả về `Stream<JumpableGenerator>`. Các generator được tạo ra **phải hỗ trợ jump**, nhưng không bắt buộc phải tiếp tục hỗ trợ leap. Không nên mặc định đối tượng con từ `leaps()` có thể gọi `leap()`.

### 5.3. Ví dụ dùng `leap()`

```java
import java.util.random.RandomGenerator.LeapableGenerator;

public class LeapBasic {
    public static void main(String[] args) {
        LeapableGenerator random =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        long first = random.nextLong();

        random.leap();

        long afterLeap = random.nextLong();

        System.out.println("Before leap: " + first);
        System.out.println("After leap:  " + afterLeap);
        System.out.println("Jump distance: " + random.jumpDistance());
        System.out.println("Leap distance: " + random.leapDistance());
    }
}
```

`Xoroshiro128PlusPlus` là một thuật toán được JDK 17 cung cấp với khả năng jump và leap. Các khoảng cách hiển thị phụ thuộc implementation; không nên dựa vào một con số cố định cho mọi thuật toán.

### 5.4. Dùng `leaps()` tạo nhóm generator

```java
import java.util.List;
import java.util.random.RandomGenerator.JumpableGenerator;
import java.util.random.RandomGenerator.LeapableGenerator;

public class LeapStream {
    public static void main(String[] args) {
        LeapableGenerator root =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        List<JumpableGenerator> workers =
                root.leaps(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

Danh sách nhận được có kiểu `JumpableGenerator`. Từng worker có thể sinh số và jump để tạo vùng con, nhưng không được giả định nó có phương thức `leap()`.

### 5.5. Mô hình hai tầng: leap cho nhóm, jump cho worker con

Ví dụ một chương trình có ba nhóm mô phỏng, mỗi nhóm có thể chia thành nhiều tác vụ nhỏ:

1. Tạo một `LeapableGenerator` gốc.
2. Gọi `leaps(3)` để tạo ba generator ở các vùng trạng thái cách xa nhau.
3. Giao mỗi generator cho một nhóm.
4. Trong từng nhóm, dùng `jumps(n)` để tạo generator cho các tác vụ con.

Mô hình:

```text
Leapable root
   |
   +-- leaps(3)
          |
          +-- Group A: Jumpable generator
          |       |
          |       +-- jumps(...) -> task A1, A2, ...
          |
          +-- Group B: Jumpable generator
          |       |
          |       +-- jumps(...) -> task B1, B2, ...
          |
          +-- Group C: Jumpable generator
                  |
                  +-- jumps(...) -> task C1, C2, ...
```

Cách này phù hợp khi chương trình có cấu trúc phân cấp rõ ràng và cần phân chia chuỗi ở hai mức độ khoảng cách khác nhau.

## 6. So sánh trực tiếp splittable, jumpable và leapable

| Tiêu chí | Splittable | Jumpable | Leapable |
|---|---|---|---|
| Thao tác trung tâm | `split()` | `jump()` | `leap()` và `jump()` |
| Tạo generator mới bằng | Chia trạng thái thành generator cha và generator con | Copy trạng thái ở các vị trí cách xa nhau trong chu trình | Copy ở các vị trí rất xa trong chu trình |
| Trạng thái generator gốc | Tiếp tục dùng và có thể split tiếp | `jump()` làm generator gốc tiến về phía trước | `leap()` làm generator gốc tiến xa hơn |
| Có thể chia tiếp? | Có, generator con cũng splittable | Generator stream trả về `RandomGenerator`; không mặc định jump tiếp | Generator stream trả về `JumpableGenerator`; có thể jump tiếp |
| Phù hợp với | Tạo tác vụ động, fork đệ quy, cấu trúc cây | Số worker biết trước, cấp vùng trạng thái theo lô | Phân chia phân cấp, nhóm lớn rồi chia nhỏ |
| Khoảng cách | Không mô tả bằng một jump distance cố định | Thường cỡ `2^64` bước hoặc hơn | Thường xa hơn jump, có thể cỡ `2^96` hoặc `2^128` tùy thuật toán |
| API stream | `splits()` | `jumps()` | `leaps()` |
| Kiểu phần tử stream | `SplittableGenerator` | `RandomGenerator` | `JumpableGenerator` |

### 6.1. Khác biệt quan trọng nhất

**Splittable tạo nhánh.** Người viết nghĩ theo cấu trúc tác vụ: tác vụ cha cần tạo tác vụ con, vì vậy tách một generator con.

**Jumpable dịch chuyển trong chu trình.** Người viết nghĩ theo vùng trạng thái: tạo các bản generator ở những vị trí cách xa nhau để cấp cho worker.

**Leapable tạo khoảng cách ở cấp cao hơn.** Người viết cần phân chia vùng lớn giữa các nhóm, sau đó dùng jump bên trong từng nhóm.

Không có quy tắc rằng leapable luôn tốt hơn jumpable hoặc splittable. Nó chỉ cung cấp thêm khả năng và phù hợp với cách tổ chức khác.

## 7. Cách chọn thuật toán trong Java 17

Các interface mô tả **khả năng**; một implementation cụ thể mới quyết định thuật toán, chu kỳ, hiệu năng và các đặc tính thống kê.

Java 17 bổ sung `RandomGeneratorFactory` để tìm và tạo generator theo tên thuật toán hoặc đặc tính.

### 7.1. Một số thuật toán thường gặp trong JDK 17

| Thuật toán | Nhóm | Khả năng thường dùng |
|---|---|---|
| `L64X128MixRandom` | LXM | Splittable |
| `L64X256MixRandom` | LXM | Splittable |
| `L128X1024MixRandom` | LXM | Splittable |
| `SplittableRandom` | Legacy | Splittable |
| `Xoroshiro128PlusPlus` | Xoroshiro | Jumpable và Leapable |
| `Xoshiro256PlusPlus` | Xoshiro | Jumpable và Leapable |

Danh sách thuật toán và đặc tính có thể được mở rộng bởi JDK hoặc provider; hãy truy vấn factory trong runtime đang triển khai thay vì hard-code giả định cho mọi môi trường.

### 7.2. Tạo generator theo tên

```java
import java.util.random.RandomGenerator;

public class ChooseAlgorithm {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        System.out.println(random.nextInt(1, 7));
    }
}
```

`RandomGenerator.of(name)` tạo generator sử dụng thuật toán có tên tương ứng. Nếu tên không được hỗ trợ, factory ném `IllegalArgumentException`.

### 7.3. Kiểm tra khả năng bằng `RandomGeneratorFactory`

Không nên đoán khả năng từ tên thuật toán. Có thể liệt kê các provider hiện có:

```java
import java.util.random.RandomGeneratorFactory;

public class ListGeneratorCapabilities {
    public static void main(String[] args) {
        RandomGeneratorFactory.all().forEach(factory -> {
            System.out.printf(
                    "%-24s split=%-5s jump=%-5s leap=%-5s deprecated=%s%n",
                    factory.name(),
                    factory.isSplittable(),
                    factory.isJumpable(),
                    factory.isLeapable(),
                    factory.isDeprecated()
            );
        });
    }
}
```

Các phương thức quan trọng:

- `name()`: tên thuật toán.
- `group()`: nhóm thuật toán.
- `period()`: chu kỳ.
- `stateBits()`: số bit trạng thái.
- `isSplittable()`: hỗ trợ split.
- `isJumpable()`: hỗ trợ jump.
- `isLeapable()`: hỗ trợ leap.
- `isArbitrarilyJumpable()`: hỗ trợ nhảy theo khoảng tùy chọn.
- `isDeprecated()`: thuật toán đã được đánh dấu deprecated hay chưa.

`RandomGeneratorFactory.all()` trả về các factory có sẵn trong runtime. Kết quả có thể khác giữa các JDK hoặc provider.

### 7.4. Chọn theo đặc điểm tác vụ

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Một luồng, không có yêu cầu đặc biệt | Một `RandomGenerator` phù hợp |
| Tác vụ fork động, nhiều nhánh đệ quy | `SplittableGenerator` |
| Nhiều worker được cấp đồng loạt từ đầu | `JumpableGenerator` hoặc `SplittableGenerator` |
| Phân cấp nhóm lớn rồi chia worker con | `LeapableGenerator`, sau đó jump |
| Cần số ngẫu nhiên cho khóa, token, dữ liệu xác thực | `SecureRandom` |

Oracle hướng dẫn `L64X128MixRandom` là lựa chọn tổng quát cân bằng tốc độ, bộ nhớ và chu kỳ trong nhiều ứng dụng không có yêu cầu đặc biệt. Tuy nhiên, lựa chọn thực tế cần xét khối lượng công việc, số luồng, số lượng generator, yêu cầu tái lập kết quả và benchmark của hệ thống.

## 8. Ví dụ tổng hợp: cấp generator riêng cho từng worker

Ví dụ sau tạo generator từ cả ba chiến lược, sau đó mỗi tác vụ nhận một instance riêng. Việc tạo danh sách generator được thực hiện tuần tự trước khi chạy parallel, để không chia sẻ generator gốc mutable trong các worker.

Lưu file **`GeneratorAllocationDemo.java`**:

```java
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGenerator.JumpableGenerator;
import java.util.random.RandomGenerator.LeapableGenerator;
import java.util.random.RandomGenerator.SplittableGenerator;
import java.util.stream.IntStream;

public class GeneratorAllocationDemo {

    private static final int TASK_COUNT = 4;

    public static void main(String[] args) {
        // 1. SPLITTABLE: tạo generator con theo từng nhánh.
        SplittableGenerator splitRoot =
                SplittableGenerator.of("L64X128MixRandom");

        List<SplittableGenerator> splitWorkers =
                splitRoot.splits(TASK_COUNT).toList();

        // 2. JUMPABLE: tạo các generator ở vùng cách xa nhau.
        JumpableGenerator jumpRoot =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        List<RandomGenerator> jumpWorkers =
                jumpRoot.jumps(TASK_COUNT).toList();

        // 3. LEAPABLE: chia vùng lớn; các generator con hỗ trợ jump.
        LeapableGenerator leapRoot =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        List<JumpableGenerator> leapWorkers =
                leapRoot.leaps(TASK_COUNT).toList();

        // Mỗi chỉ số nhận một generator riêng.
        System.out.println("SPLITTABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = splitWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });

        System.out.println("JUMPABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = jumpWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });

        System.out.println("LEAPABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = leapWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 GeneratorAllocationDemo.java
java GeneratorAllocationDemo
```

Chương trình in một giá trị cho mỗi tác vụ trong mỗi chiến lược. Các giá trị cụ thể thay đổi theo trạng thái khởi tạo và không có thứ tự in cố định khi dùng parallel stream.

### 8.1. Vì sao tạo danh sách trước khi chạy parallel?

`splitRoot`, `jumpRoot` và `leapRoot` đều là generator mutable. Chúng được dùng tuần tự để tạo các generator worker. Sau đó, mỗi worker chỉ sử dụng generator ở chỉ số riêng.

Mô hình này giúp tránh việc nhiều thread cùng thao tác trên một generator gốc. Nó cũng làm rõ quyền sở hữu trạng thái:

- Giai đoạn chuẩn bị: một luồng quản lý generator gốc.
- Giai đoạn thực thi: mỗi tác vụ có generator riêng.
- Không có một instance generator được nhiều worker cùng gọi `nextLong()`.

Nếu tác vụ tự fork trong lúc chạy, `SplittableGenerator` có thể phù hợp hơn vì mỗi worker có thể split từ generator mà nó sở hữu.

## 9. Giới hạn và nguyên tắc an toàn khi phân vùng chuỗi

### 9.1. Không dùng chung instance mutable giữa các thread

Đây là quy tắc quan trọng nhất. Hãy phân phối generator riêng cho mỗi worker, và không để nhiều thread cùng thay đổi trạng thái của cùng một generator nếu implementation không cam kết thread-safe.

### 9.2. Khoảng cách jump/leap không phải vùng vô hạn

Nếu một generator được tạo ra từ khoảng jump cố định rồi sinh số vượt xa vùng được dự kiến dành cho nó, chuỗi có thể tiến đến vùng của generator khác. Các tài liệu API nêu giả định về số lượng giá trị mà mỗi generator tạo ra so với khoảng cách jump và chu kỳ.

Vì vậy:

- Chọn thuật toán có period phù hợp.
- Hiểu giới hạn sử dụng của thuật toán.
- Không mặc định có thể sinh vô hạn giá trị từ mỗi generator con mà vẫn giữ các vùng tách biệt.
- Đối với mô phỏng dài, cần tính toán số lượng mẫu và khoảng cách phân vùng.

### 9.3. Split/jump/leap không phải cơ chế bảo mật

Các PRNG trong nhóm này chủ yếu phục vụ mô phỏng, game, tính toán khoa học và tác vụ song song. Chúng thường **không an toàn về mặt mật mã**.

Không dùng chúng để sinh:

- Mật khẩu hoặc khóa bí mật.
- Session token.
- Reset token.
- OTP hoặc mã xác thực.
- Nonce cần chống dự đoán trong giao thức bảo mật.

Dùng `java.security.SecureRandom` cho các yêu cầu cần PRNG an toàn về mật mã.

### 9.4. Tái lập kết quả khi chạy song song

Nếu cần tái hiện một lần chạy để debug:

- Chọn thuật toán rõ ràng thay vì phụ thuộc generator mặc định.
- Ghi nhận seed và phiên bản JDK/implementation khi phù hợp.
- Cấp generator theo ID tác vụ ổn định.
- Không dựa vào thứ tự worker được scheduler chạy.
- Không thay đổi số lần gọi random tùy tiện giữa các nhánh nếu cần chuỗi kết quả tái lập.

Cùng seed không tự động đảm bảo hai chương trình song song tạo cùng kết quả nếu thứ tự cấp phát generator hoặc thứ tự tiêu thụ số thay đổi.

## 10. Các hiểu nhầm thường gặp

### 10.1. “Splittable và jumpable đều là tạo một bản copy”

Không hoàn toàn. `split()` tạo generator con theo chiến lược split của thuật toán; `jump()` dịch chuyển trạng thái generator hiện tại. Stream `jumps()` mới tạo các bản copy ở những vị trí sau các lần jump.

### 10.2. “Jumpable có thể leap”

Không. `JumpableGenerator` chỉ cung cấp jump. `LeapableGenerator` mở rộng nó và bổ sung leap.

### 10.3. “Leapable là interface hoàn toàn tách biệt”

Không. `LeapableGenerator extends JumpableGenerator`, vì vậy mọi leapable đều có khả năng jump.

### 10.4. “`jumps()` trả về stream của JumpableGenerator”

Không. Trong Java 17, kiểu trả về của `jumps()` là `Stream<RandomGenerator>`. Không nên ép kiểu phần tử về `JumpableGenerator`.

### 10.5. “`leaps()` trả về stream của LeapableGenerator”

Không. `leaps()` trả về `Stream<JumpableGenerator>`. Generator con phải jump được, nhưng không bắt buộc leap được.

### 10.6. “Các chuỗi được split/jump/leap chắc chắn không có giá trị nào trùng nhau”

Sai. Các chuỗi hướng tới độc lập thống kê; giá trị đầu ra vẫn có thể trùng ngẫu nhiên. Mục tiêu là giảm tương quan và tránh dùng chồng lấn vùng trạng thái theo cách không phù hợp.

### 10.7. “Có thể dùng cùng một generator cho nhiều thread nếu gọi split”

Không nên chia sẻ cùng generator cha giữa các thread. Hãy để một thread sở hữu generator cha, gọi split khi fork, rồi chuyển generator con cho worker mới.

### 10.8. “Generator con từ `leaps()` tiếp tục leap được”

Không có bảo đảm đó. Kiểu trả về là `JumpableGenerator`. Dùng phương thức được kiểu trả về cam kết.

### 10.9. “Các generator này dùng cho token bảo mật”

Không. Dùng `SecureRandom` cho dữ liệu nhạy cảm và yêu cầu an toàn mật mã.

## 11. Quy trình lựa chọn thực tế

Khi thiết kế một hệ thống đa luồng, có thể đi theo các bước sau:

1. **Xác định mục đích:** mô phỏng, game, test, thống kê hay bảo mật. Nếu bảo mật, chọn `SecureRandom`.
2. **Xác định cấu trúc tác vụ:** fork động và đệ quy hay cấp worker theo lô.
3. **Chọn interface:** `SplittableGenerator` cho fork động; `JumpableGenerator` cho phân vùng chu trình theo khoảng cố định; `LeapableGenerator` cho hai tầng khoảng cách.
4. **Chọn thuật toán:** dùng `RandomGeneratorFactory` để kiểm tra khả năng và đặc tính.
5. **Tạo generator riêng:** mỗi worker sở hữu instance của nó.
6. **Xác định khối lượng sinh số:** không để mỗi worker vượt quá giả định về khoảng cách/chu kỳ của thuật toán.
7. **Kiểm thử và benchmark:** xem tốc độ, bộ nhớ, số lượng worker và tính chất thống kê phù hợp với ứng dụng.

### Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “có” | Gợi ý |
|---|---|---|
| Tác vụ liên tục fork thành các tác vụ con mới? | Có | Splittable |
| Số worker được biết trước và cần cấp vùng trạng thái theo lô? | Có | Jumpable |
| Có nhiều nhóm lớn, mỗi nhóm lại chia worker con? | Có | Leapable ở tầng nhóm, jump ở tầng con |
| Chỉ có một luồng? | Có | RandomGenerator phù hợp, không cần split/jump/leap |
| Cần tạo khóa hoặc token không thể dự đoán? | Có | SecureRandom |

## 12. Bài tập tự luyện

### Bài 1. Chọn interface cho tác vụ fork động

Một worker xử lý cây dữ liệu. Trong quá trình duyệt, mỗi node có thể tạo từ 0 đến nhiều tác vụ con. Mỗi tác vụ cần chuỗi giả ngẫu nhiên riêng.

**Đáp án gợi ý:** `SplittableGenerator` phù hợp vì mỗi worker có thể gọi `split()` khi fork và chuyển generator con cho tác vụ mới.

### Bài 2. Chọn interface cho một batch cố định

Một mô phỏng bắt đầu với 32 worker đã biết trước. Cần tạo các generator ở những vùng xa nhau của chu trình.

**Đáp án gợi ý:** Có thể dùng `JumpableGenerator` và `jumps(32)`, hoặc splittable nếu cách phân chia phù hợp với thuật toán. Với jump, hãy kiểm tra số mẫu mỗi worker dự kiến sinh so với khoảng cách jump.

### Bài 3. Phân chia hai tầng

Một chương trình có 8 nhóm thí nghiệm; mỗi nhóm có 16 worker.

**Đáp án gợi ý:** Có thể dùng `LeapableGenerator` để tạo 8 generator nhóm qua `leaps(8)`, rồi dùng `jumps(16)` trên từng generator nhóm. Nhớ rằng phần tử của `leaps()` là `JumpableGenerator`.

### Bài 4. Đọc kiểu trả về

Cho:

```java
LeapableGenerator root = LeapableGenerator.of("Xoroshiro128PlusPlus");
var children = root.leaps(4);
```

**Câu hỏi:** Mỗi phần tử của `children` có chắc chắn là `LeapableGenerator` không?

**Đáp án:** Không. `leaps()` trả về `Stream<JumpableGenerator>`. Các phần tử phải hỗ trợ jump, không bắt buộc hỗ trợ leap.

### Bài 5. Giải thích vì sao không chia sẻ generator

Một lập trình viên khai báo một biến `SplittableGenerator root` rồi cho tất cả thread gọi `root.split()` cùng lúc.

**Đáp án:** Đây là chia sẻ một đối tượng mutable giữa nhiều thread. Hãy để một thread sở hữu generator gốc và thực hiện split trước khi chuyển generator con cho các worker; hoặc dùng cấu trúc sở hữu generator riêng theo từng nhánh.

### Bài 6. Phân biệt giá trị trùng và chuỗi trùng

Hai worker đều sinh được giá trị `17` ở lần gọi đầu tiên.

**Đáp án:** Điều này có thể xảy ra tự nhiên và không chứng minh các chuỗi trùng nhau. Cần xét đặc tính thống kê và vùng trạng thái, không chỉ một giá trị đầu ra.

### Bài 7. Lựa chọn cho token đăng nhập

Một hệ thống cần sinh token phiên đăng nhập khó đoán.

**Đáp án:** Dùng `SecureRandom`. `SplittableGenerator`, `JumpableGenerator` và `LeapableGenerator` chủ yếu phục vụ PRNG cho tính toán, không phải cơ chế an toàn mật mã.

## 13. Tài liệu tham khảo chính thức

- [JDK 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface gốc và các phương thức sinh số.
- [JDK 17 API — SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html): `split()`, `splits()` và quy tắc tạo generator con.
- [JDK 17 API — JumpableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.JumpableGenerator.html): `jump()`, `copy()`, `jumps()` và khoảng cách jump.
- [JDK 17 API — LeapableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.LeapableGenerator.html): quan hệ kế thừa từ Jumpable, `leap()`, `leaps()` và khoảng cách leap.
- [JDK 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): chọn thuật toán và truy vấn khả năng splittable, jumpable, leapable.
- [Oracle Java 17 — Pseudorandom Number Generators](https://docs.oracle.com/en/java/javase/17/core/pseudorandom-number-generators.html): cách dùng các generator trong ứng dụng đa luồng và gợi ý chọn thuật toán.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): thiết kế API PRNG được bổ sung trong Java 17.

**Ghi nhớ:** `SplittableGenerator` tạo generator con bằng `split()` và phù hợp với tác vụ fork động. `JumpableGenerator` dịch chuyển trạng thái theo khoảng cố định và tạo stream generator bằng `jumps()`. `LeapableGenerator` kế thừa jump, bổ sung bước leap xa hơn để phân chia theo tầng. Hãy cấp generator riêng cho từng worker, kiểm tra kiểu trả về thực tế của stream và dùng `SecureRandom` cho mọi nhu cầu bảo mật.
