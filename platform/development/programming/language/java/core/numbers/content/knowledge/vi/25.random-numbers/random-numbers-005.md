# SplittableRandom và chia nguồn ngẫu nhiên trong Java

## 1. Vấn đề: vì sao cần “chia” nguồn sinh số ngẫu nhiên?

Khi chương trình chỉ chạy một chuỗi thao tác, ta có thể tạo một bộ sinh số giả ngẫu nhiên (*pseudorandom number generator*, PRNG) rồi gọi lần lượt `nextInt()`, `nextLong()` hoặc `nextDouble()`. Trong ứng dụng thực tế, công việc có thể tách thành nhiều nhánh: mô phỏng nhiều kịch bản, xử lý một tập dữ liệu theo các tác vụ độc lập hoặc dùng `ExecutorService` / fork-join để chạy song song.

Nếu nhiều tác vụ cùng dùng **một đối tượng sinh số có trạng thái**, chúng có thể tranh chấp trạng thái, gây khó tái lập kết quả hoặc vi phạm hợp đồng về an toàn luồng. `java.util.SplittableRandom` giải quyết bài toán này bằng thao tác **`split()`**: tạo một đối tượng sinh số mới cho nhánh con. Mỗi nhánh sở hữu bộ sinh riêng và tự lấy các số tiếp theo mà không phải truy cập cùng một generator.

`SplittableRandom` xuất hiện từ Java 8, có trong Java 17+, phù hợp với việc tạo dữ liệu ngẫu nhiên hiệu năng tốt và các phép tính chia nhánh. Đây là **bộ sinh giả ngẫu nhiên**, không phải nguồn ngẫu nhiên mật mã; kết quả phụ thuộc trạng thái và thuật toán, không bảo đảm bí mật hay khó dự đoán trước khi kẻ tấn công biết seed/trạng thái.

Mục tiêu sau bài học: hiểu `split()` làm gì; cách tổ chức cây generator cha-con; cách cung cấp seed để tái lập; cách cấp một generator cho từng tác vụ; cách dùng phạm vi giá trị của API; và những trường hợp phải chọn giải pháp khác.

## 2. Tạo SplittableRandom và gọi các phương thức cơ bản

Hai cách tạo thường gặp:

```java
import java.util.SplittableRandom;

// Seed tường minh: phù hợp cho thử nghiệm có thể tái lập.
SplittableRandom reproducible = new SplittableRandom(2026L);

// Không truyền seed: hệ thống tạo seed ban đầu.
SplittableRandom ordinary = new SplittableRandom();
```

Những API thường dùng:

| Phương thức | Ý nghĩa | Phạm vi |
|---|---|---|
| `nextInt()` | Số nguyên 32-bit giả ngẫu nhiên | Toàn bộ miền của `int` |
| `nextLong()` | Số nguyên 64-bit giả ngẫu nhiên | Toàn bộ miền của `long` |
| `nextDouble()` | Số thực từ 0 tới dưới 1 | `[0.0, 1.0)` |
| `nextInt(10)` | Số nguyên từ 0 tới dưới 10 | `0..9` |
| `nextInt(5, 15)` | Số nguyên từ 5 tới dưới 15 | `5..14` |
| `nextLong(10L, 20L)` | Số `long` từ 10 tới dưới 20 | `10..19` |
| `ints(5, 0, 10)` | `IntStream` có 5 phần tử trong khoảng 0 đến dưới 10 | Mỗi phần tử `0..9` |
| `split()` | Sinh một `SplittableRandom` con để cấp cho nhánh công việc | Generator mới |

Các khoảng có cận trên **loại trừ** (*exclusive*). Vì thế, `nextInt(10)` không trả 10. Với các overload có `origin` và `bound`, phải có `origin < bound`; `nextInt(0)` hoặc `nextInt(10, 10)` là yêu cầu không hợp lệ và ném `IllegalArgumentException`.

Phương thức `ints(...)` tạo luồng giá trị `int` để xử lý bằng Stream API. Đây là **luồng số lấy từ một generator**, khác với `splits(...)` (Java 17+) tạo luồng **các generator con**. Khi một stream số được tiêu thụ, generator liên quan tiến trạng thái theo các lần sinh giá trị.

## 3. split() hoạt động như thế nào?

`SplittableRandom` là đối tượng **có trạng thái** (*stateful*). Mỗi lần gọi `nextInt()` hoặc các phương thức sinh số, trạng thái tiến lên. `split()` cũng sử dụng và cập nhật trạng thái của generator cha để tạo **generator con mới với trạng thái riêng**. Sau `split()`:

1. Generator cha **vẫn sử dụng được** để sinh số hoặc tạo các nhánh khác.
2. Generator con là **đối tượng riêng**, có thể tiến trạng thái độc lập với cha và các con khác.
3. Không nên coi con là bản sao có cùng chuỗi số với cha; mục tiêu của thao tác chia là tạo các dòng giả ngẫu nhiên **được thiết kế để ít tương quan**, không phải nhân bản y hệt.
4. Lời gọi `split()` có ảnh hưởng đến trạng thái cha. Vì vậy **thứ tự chia**, số lần chia và thứ tự lấy số là một phần của diễn tiến generator.

Minh họa cách cấp generator cho cây tác vụ:

```text
root = new SplittableRandom(seed)
   |
   +-- root.split() --> generator A --> các lần nextInt riêng của task A
   |
   +-- root.split() --> generator B --> các lần nextInt riêng của task B
   |
   +-- root.split() --> generator C --> các lần nextInt riêng của task C
   |
   +-- root vẫn có thể split tiếp hoặc tự sinh số
```

Điểm cần nhớ: **chia generator trước khi giao công việc cho từng tác vụ**. Sau khi giao, mỗi tác vụ chỉ dùng generator của mình. Không nên đồng thời gọi `root.split()` trên cùng đối tượng `root` từ nhiều luồng.

Không cần và không nên trông chờ mỗi generator con đều sinh ra các số **không bao giờ trùng nhau**. Hai nhánh độc lập vẫn có thể tình cờ sinh cùng một số, chẳng hạn cùng nhận `7` từ `nextInt(10)`. “Chia nguồn” nói về việc tổ chức trạng thái và chất lượng các dòng ngẫu nhiên, **không phải cam kết mọi giá trị xuất ra đều duy nhất**.

### Vì sao không tự tạo các generator bằng cùng seed?

Đoạn sau là một lỗi thường gặp:

```java
SplittableRandom a = new SplittableRandom(2026L);
SplittableRandom b = new SplittableRandom(2026L);
```

Nếu hai đối tượng cùng seed và dùng cùng chuỗi lời gọi, chúng cho **cùng chuỗi giá trị**. Đây là điều có ích cho kiểm thử tái lập, nhưng không phải cách cấp hai luồng giả ngẫu nhiên khác nhau cho hai tác vụ. Nếu đã có một generator gốc, dùng `root.split()` để lấy từng nguồn con.

Cũng không cần mô phỏng `split()` bằng `new SplittableRandom(root.nextLong())`. API `split()` đã được thiết kế riêng cho việc tạo generator con và quản lý trạng thái chia nguồn; hãy dùng đúng API.

## 4. Ví dụ Java 17+: hai nhánh và hai tác vụ song song

Tạo file **`RandomSplitDemo.java`** với chương trình chạy độc lập dưới đây:

```java
import java.util.Arrays;
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RandomSplitDemo {
    private static int[] draw(SplittableRandom rng) {
        // Đúng 5 số, mỗi số thuộc [0, 10).
        return rng.ints(5, 0, 10).toArray();
    }

    private static int[][] makePair(long seed) {
        SplittableRandom root = new SplittableRandom(seed);

        // Thứ tự chia nguồn cố định.
        SplittableRandom childA = root.split();
        SplittableRandom childB = root.split();

        return new int[][] {draw(childA), draw(childB)};
    }

    private static int[] parallelSums(long seed) throws Exception {
        SplittableRandom root = new SplittableRandom(seed);

        // Tạo cả hai nguồn ở luồng điều phối trước khi submit.
        SplittableRandom rngA = root.split();
        SplittableRandom rngB = root.split();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> a = pool.submit(
                    () -> rngA.ints(1000, 0, 10).sum());
            Future<Integer> b = pool.submit(
                    () -> rngB.ints(1000, 0, 10).sum());

            // Đọc theo thứ tự nhiệm vụ A rồi B.
            return new int[] {a.get(), b.get()};
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        int[][] first = makePair(2026L);
        int[][] again = makePair(2026L);

        System.out.println("repeatable: "
                + Arrays.deepEquals(first, again));

        System.out.println("two children, five numbers each: "
                + (first.length == 2
                && first[0].length == 5
                && first[1].length == 5));

        System.out.println("range [0, 10): "
                + Arrays.stream(first)
                        .flatMapToInt(Arrays::stream)
                        .allMatch(n -> n >= 0 && n < 10));

        int[] p1 = parallelSums(2026L);
        int[] p2 = parallelSums(2026L);

        System.out.println("parallel repeatable: "
                + Arrays.equals(p1, p2));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac RandomSplitDemo.java
java RandomSplitDemo
```

Kết quả:

```text
repeatable: true
two children, five numbers each: true
range [0, 10): true
parallel repeatable: true
```

Giải thích từng phần:

- `makePair(2026L)` tạo generator cha với seed cố định, sau đó **chia A trước B**, rồi mỗi con sinh 5 số. Gọi lại với cùng seed và cùng trình tự tạo/chạy cho cùng hai mảng; kiểm tra dùng `Arrays.deepEquals` vì dữ liệu có kiểu `int[][]`.
- `ints(5, 0, 10)` lấy đúng 5 phần tử trong khoảng `[0,10)`. Kiểm tra `allMatch` xác nhận quy tắc về cận; đây không phải phép kiểm định chất lượng thống kê.
- `parallelSums` cấp `rngA` và `rngB` riêng biệt **trước khi** gọi `submit`. Mỗi tác vụ tính tổng 1.000 giá trị nguyên bằng generator của mình. Không có hai tác vụ cùng truy cập một `SplittableRandom`.
- Gọi `Future.get()` chờ kết quả hoàn tất. Kết quả hai lần giống nhau vì cùng seed, cùng thứ tự split và mỗi nhánh tiêu thụ số lần lấy giá trị cố định. Thứ tự hai công việc được hệ điều hành xếp chạy không ảnh hưởng đến trạng thái generator của nhánh kia.
- `pool.shutdown()` ở `finally` đóng executor sau khi dùng. Đây là phần quản lý tài nguyên, không liên quan đến thuật toán tạo số ngẫu nhiên.

Chương trình chủ ý in **tính chất có thể kiểm chứng** thay vì chép mười số giả ngẫu nhiên cụ thể. Nếu cần xem giá trị thực, thêm `System.out.println(Arrays.deepToString(first));`. Các số có thể trùng giữa hai nhánh mà điều đó không làm sai cơ chế `split()`.

## 5. Tính tái lập: seed là cần thiết nhưng chưa đủ

Với `new SplittableRandom(seed)`, một luồng gọi hàm **cố định** sẽ tái lập chuỗi sinh ra. Khi tạo cây generator, kết quả còn phụ thuộc cách chia và cách dùng từng nhánh.

Để một phép thử tái lập ổn định, cố định tất cả yếu tố:

1. **Seed gốc**: cùng seed khi khởi tạo generator cha.
2. **Cấu trúc phân nhánh**: cùng số lượng `split()`, cùng thứ tự tạo A, B, C.
3. **Phân công nguồn**: cùng nhánh công việc nhận đúng generator con của nó.
4. **Trình tự và số lượng lời gọi trong từng nhánh**: ví dụ mỗi nhánh gọi `nextInt(100)` chính xác 1.000 lần.
5. **Dữ liệu và thuật toán xử lý**: nếu thay đổi điều kiện hoặc thứ tự gọi ngẫu nhiên, kết quả đầu ra cũng có thể đổi.

Ví dụ này **không bảo đảm tái lập** dù seed giống nhau:

```java
SplittableRandom shared = new SplittableRandom(2026L);

// Không dùng cùng một shared trong hai tác vụ chạy song song.
// Việc luồng nào gọi nextInt() trước còn tùy thời điểm chạy.
```

Ngoài vấn đề tái lập, cách chia sẻ trên còn sai về an toàn luồng. Một lỗi tinh vi khác là để từng tác vụ gọi `root.split()` đồng thời: như vậy generator cha trở thành trạng thái chia sẻ. Cách đơn giản và đúng là tạo nguồn con **ở luồng điều phối** rồi giao từng nguồn cho một tác vụ.

Nếu chia việc động (ví dụ fork-join sinh thêm nhiệm vụ tùy dữ liệu), nhánh tạo nhiệm vụ có thể gọi `split()` trên **generator do chính nhánh đó sở hữu** rồi giao con cho nhiệm vụ mới. Điều kiện là không có hai nhiệm vụ cùng thao tác trên một generator tại cùng thời điểm. Muốn tái lập xuyên các lần chạy, cấu trúc chia và lượng dữ liệu tiêu thụ cũng cần ổn định, hoặc cần một chiến lược seed gắn với định danh tác vụ đã được thiết kế rõ ràng.

### Cùng seed không có nghĩa kết quả luôn giống qua mọi thay đổi mã

Nếu thêm một lời gọi `nextInt()` trước `split()`, đổi thứ tự `split()`, hoặc chuyển nhánh nào tiêu thụ bao nhiêu số, các chuỗi tiếp theo có thể đổi. Vì vậy đừng xem seed đơn lẻ như “ảnh chụp” toàn bộ trạng thái một phép tính song song.

Một bộ kiểm thử có thể ghi lại seed, cấu trúc phân nhánh và phiên bản thuật toán nếu việc phát lại chuỗi là yêu cầu quan trọng. Với ví dụ trong một lần chạy trên cùng JDK, việc cố định seed và trình tự thao tác có thể kiểm tra được như chương trình ở trên.

## 6. An toàn luồng và hiệu năng: mỗi tác vụ một generator

Tài liệu API của Java nêu rõ các đối tượng `SplittableRandom` **không thread-safe**: không được coi một instance là tài nguyên dùng đồng thời an toàn giữa nhiều luồng. Chúng được thiết kế để **chia ra và sở hữu riêng**, phù hợp với các phép tính phân nhánh, nhất là fork-join.

Quy tắc tổ chức:

| Cách dùng | Đánh giá | Lý do |
|---|---|---|
| Một luồng duy nhất dùng một `SplittableRandom` | Phù hợp | Không có truy cập đồng thời |
| Cha `split()` tuần tự rồi mỗi task nhận một con | Phù hợp | Trạng thái từng generator độc lập theo chủ sở hữu |
| Hai task cùng gọi `nextInt()` trên cùng instance | Tránh | `SplittableRandom` không thread-safe |
| Nhiều task cùng gọi `split()` trên cùng cha | Tránh | Cùng sửa trạng thái cha, có thể tranh chấp |
| Mỗi task tạo `new SplittableRandom(2026L)` | Thường không phù hợp | Các task có thể sinh cùng chuỗi nếu thao tác giống nhau |
| Mỗi task giữ generator của mình và con tạo việc nhỏ hơn bằng `split()` | Phù hợp khi quản lý sở hữu chặt | Tạo cấu trúc chia đệ quy, không chia sẻ đối tượng |

**Hiệu năng:** ý tưởng chia nguồn giúp giảm nhu cầu đồng bộ hóa quanh một generator chung trong các công việc song song. Tuy nhiên, nó **không tự làm mọi thuật toán nhanh hơn**: thời gian tạo tác vụ, gom kết quả và số lượng phép tính vẫn quyết định hiệu năng thực tế. Khi công việc rất nhỏ, overhead của song song có thể lớn hơn lợi ích. Không cần tự gọi `split()` cho mọi số ngẫu nhiên đơn lẻ; hãy tạo một generator cho mỗi **đơn vị công việc độc lập** và dùng nhiều lần.

## 7. So sánh với Random, ThreadLocalRandom và SecureRandom

| API | Cách quản lý | Khi nào phù hợp |
|---|---|---|
| `java.util.Random` | PRNG dùng tuần tự; có thể chia sẻ nhưng đồng thời có thể gây tranh chấp | Mã truyền thống, tác vụ đơn giản, yêu cầu API cũ |
| `ThreadLocalRandom.current()` | Generator riêng gắn với luồng thực thi, do thư viện quản lý | Khi muốn tiện lợi trong mã đa luồng và không cần tự kiểm soát seed cho từng tác vụ |
| `SplittableRandom` | PRNG có thể chia thành nhiều generator con bằng `split()` | Thuật toán phân nhánh, fork-join, mô phỏng nhiều tác vụ, tái lập qua seed + cấu trúc chia ổn định |
| `java.security.SecureRandom` | Bộ sinh dành cho yêu cầu bảo mật | Token, nonce, khóa và các giá trị cần tính khó dự đoán phù hợp yêu cầu bảo mật |

`ThreadLocalRandom.current()` hữu ích khi mỗi luồng đơn giản muốn lấy số mà không chia sẻ một `Random` chung, nhưng generator gắn với luồng không đồng nghĩa với generator gắn với **tác vụ logic**: tác vụ có thể chạy trên các luồng khác nhau. `SplittableRandom` cho phép giao **một instance cụ thể cho đúng tác vụ**, dễ kiểm soát ở mô hình chia nhánh.

Không dùng `SplittableRandom` để sinh mật khẩu, session token, mã khôi phục, khóa hoặc dữ liệu bí mật. Biết seed hoặc đoán được trạng thái có thể khiến chuỗi số giả ngẫu nhiên dự đoán được; trong các trường hợp bảo mật, dùng API `SecureRandom` phù hợp.

### Quan hệ với RandomGenerator trong Java 17

Java 17 cung cấp họ interface `java.util.random.RandomGenerator`. `SplittableRandom` thực hiện `RandomGenerator.SplittableGenerator`, hỗ trợ các khả năng chia nguồn trong API thống nhất. `SplittableRandom.split()` trả về `SplittableRandom`, nên có thể trực tiếp gán con vào biến cùng kiểu. Trong Java 17+ cũng có các phương thức thuộc mô hình `splits()` / `splits(long)` để tạo stream các generator con.

Ví dụ tạo ba generator con:

```java
import java.util.List;
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);
List<SplittableRandom> children = root.splits(3).toList();

// 3 nguồn riêng; sau đó giao mỗi nguồn cho một tác vụ.
```

Đoạn trên là **mã minh họa đặt trong một phương thức** (không phải chương trình độc lập). `toList()` của Stream có từ Java 16. `splits(3)` sinh stream gồm ba generator; việc tiêu thụ stream sẽ thực hiện các lần chia, nên phải có chiến lược sở hữu rõ ràng, nhất là nếu chọn pipeline song song. Đối với số tác vụ cố định và cần dễ kiểm tra thứ tự, vòng lặp `root.split()` tuần tự thường dễ hiểu hơn.

## 8. Lỗi thường gặp và cách kiểm tra

### Nhầm việc chia nguồn với chia dải số

`root.split()` **không** có nghĩa A chỉ sinh số từ 0–4, còn B chỉ sinh 5–9. Cả A và B vẫn có thể gọi `nextInt(0, 10)` và sinh ra bất kỳ số nào trong `[0,10)`. Chia nguồn phân tách **trạng thái PRNG**, không phân vùng kết quả đầu ra.

Nếu bài toán yêu cầu ID không trùng hoặc phân bổ chính xác từng giá trị, hãy dùng chiến lược cấp ID, phân đoạn tập giá trị hoặc khóa/transaction thích hợp. Nguồn số ngẫu nhiên độc lập không thay thế các đảm bảo tính duy nhất.

### Cho rằng split “nhân đôi” trạng thái cha

Nếu tạo `child = root.split()` rồi gọi `child.nextInt()` và `root.nextInt()`, không có yêu cầu hai kết quả giống nhau. `split()` sinh một generator mới; đây không phải `clone()`, không phải copy object và không phải phép “đánh dấu” mà không đổi trạng thái cha.

### Dùng cùng generator ở nhiều luồng và thấy đôi lúc vẫn chạy

Việc chương trình ít tải chưa xuất hiện lỗi không chứng minh dùng chung generator là an toàn. Truy cập đồng thời vào generator không thread-safe có thể gây dữ liệu không đúng kỳ vọng và phá tính tái lập. Luôn thiết lập chủ sở hữu của mỗi generator theo nhiệm vụ.

### Đổi thứ tự tạo nhánh nhưng vẫn kỳ vọng kết quả giống

Nếu lần một A dùng con của `split()` thứ nhất còn lần hai A nhận con thứ hai, chuỗi của A có thể đổi. Khi xây test song song cần cố định cách ánh xạ **tác vụ → generator con**. Chỉ fixed seed là không đủ khi lịch chia hoặc tiêu thụ nguồn thay đổi.

### Nhầm ngẫu nhiên giả với bảo mật hoặc “ngẫu nhiên thật”

`SplittableRandom` có chất lượng PRNG hữu ích cho nhiều phép mô phỏng và chia nhánh, nhưng không cung cấp tính chất mật mã. Và ngay cả với các nhánh riêng, không có lời hứa rằng mỗi số sinh ra đều khác tất cả số trước đó. Kiểm tra dữ liệu theo xác suất, phân phối, miền giá trị và yêu cầu ứng dụng; đừng rút kết luận thống kê từ một vài mẫu.

### Tạo quá nhiều generator hoặc tác vụ

Có thể chia cây generator sâu theo cây công việc, nhưng mỗi nguồn và mỗi tác vụ đều có chi phí. Nếu chỉ cần lấy một chuỗi 10.000 số ở một luồng, một generator duy nhất thường đơn giản hơn. Chỉ chia nguồn khi thật sự có **công việc độc lập**, nhất là khi thực thi song song.

## 9. Cách áp dụng và tự kiểm tra

Để dùng `SplittableRandom` cho một tác vụ gồm N nhánh:

1. Tạo `root`. Dùng seed cố định cho kiểm thử; cân nhắc nguồn seed phù hợp khi chạy thực tế.
2. Xác định các nhánh có thể tính độc lập và nhánh nào cần bộ sinh riêng.
3. Ở luồng điều phối, gọi `root.split()` đúng một lần cho mỗi nhánh và **gắn con với định danh nhánh**.
4. Giao mỗi con cho một tác vụ; tác vụ chỉ thao tác trên generator của mình.
5. Khi tác vụ tự chia nhỏ, chỉ generator của tác vụ đó mới được dùng để `split()` thêm.
6. Nếu cần tái lập, giữ cố định seed, cây chia, thứ tự ánh xạ và lượng lời gọi; viết test so sánh kết quả của hai lần chạy.
7. Không dùng `SplittableRandom` cho mục đích mật mã.

**Tự kiểm tra 1:** Hai tác vụ đều dùng `new SplittableRandom(7L)` và cùng gọi `nextInt(100)` ba lần. Chúng có tạo hai dòng khác nhau không? **Không:** cùng seed và chuỗi lời gọi dẫn đến cùng chuỗi kết quả. Nên chia từ một generator cha nếu muốn hai nguồn khác nhau.

**Tự kiểm tra 2:** Gọi `SplittableRandom child = root.split()`, rồi task A dùng `root` còn task B dùng `child` có hợp lệ không? **Có**, nếu không luồng nào khác dùng cùng các đối tượng đó trong khi chạy. Cha vẫn sử dụng được; tuy nhiên để dễ quản lý, thường cấp riêng từng con và giữ cha làm bộ điều phối.

**Tự kiểm tra 3:** Task A và task B cùng trả `5` từ `nextInt(10)`. Điều này có chứng minh `split()` bị lỗi không? **Không**. Hai dòng giả ngẫu nhiên có thể xuất ra cùng một giá trị. Điều quan trọng là trạng thái và truy cập được quản lý riêng.

**Ghi nhớ:** `SplittableRandom` là PRNG **có thể chia**. Gọi `split()` ở nhánh đang sở hữu generator rồi **giao con cho tác vụ độc lập**. Cùng seed và cùng cấu trúc chia/cách tiêu thụ giúp kiểm thử tái lập; chia nguồn không bảo đảm giá trị duy nhất, không tự bảo đảm tăng tốc và không cung cấp bảo mật mật mã.
