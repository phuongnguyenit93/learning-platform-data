# Stream giá trị ngẫu nhiên và giới hạn kích thước trong Java

Khi cần tạo 5 mặt xúc xắc, 1.000 điểm dữ liệu thử nghiệm hoặc một luồng số ngẫu nhiên để xử lý từng phần, Java có thể tạo trực tiếp `IntStream`, `LongStream` và `DoubleStream`. Thay vì tạo và lưu một mảng rất lớn từ đầu, ta khai báo nguồn phát số, giới hạn số phần tử và gắn các phép biến đổi trước khi thực thi.

Có hai câu hỏi phải tách biệt:

1. **Phạm vi giá trị:** Mỗi số được lấy trong khoảng nào? Ví dụ xúc xắc cần số nguyên từ 1 đến 6, tức khoảng Java `[1, 7)`.
2. **Kích thước luồng:** Tạo bao nhiêu phần tử? Ví dụ 5 lần tung xúc xắc, tức `streamSize = 5` hoặc `limit(5)`.

Phạm vi giá trị (`origin`, `bound`) và kích thước luồng (`streamSize`, `limit`) hoàn toàn khác nhau. Bài này trình bày cách tạo nguồn số ngẫu nhiên Java 17+, cách giới hạn luồng, ảnh hưởng của thứ tự các phép toán, cơ chế lazy, tài nguyên và những lỗi thường gặp.

## 1. Stream số ngẫu nhiên là gì?

Java Stream là một **pipeline xử lý dữ liệu**, không phải một collection chứa sẵn các phần tử. Với số ngẫu nhiên, nguồn như `Random.ints()` cung cấp các giá trị khi pipeline cần chúng. Phần xử lý có thể gồm `map`, `filter`, `limit`; terminal operation như `toArray`, `sum`, `forEach` hay `count` kích hoạt pipeline.

~~~text
Random / RandomGenerator
          |
          v
  ints / longs / doubles
          |
          v
 filter / map / limit / skip  (nếu có)
          |
          v
  toArray / sum / forEach ...  (terminal)
~~~

Ba dạng primitive stream tránh phải đóng hộp từng `int`, `long` và `double` thành đối tượng `Integer`, `Long`, `Double` trong nhiều phép toán.

| Nguồn | Kiểu stream | Kiểu phần tử |
|---|---|---|
| `random.ints(...)` | `IntStream` | `int` |
| `random.longs(...)` | `LongStream` | `long` |
| `random.doubles(...)` | `DoubleStream` | `double` |
| `Stream.generate(supplier)` | `Stream<T>` | Kiểu đối tượng được `Supplier` sinh ra |

Một luồng ngẫu nhiên **có thể hữu hạn hoặc hiệu quả là vô hạn**. JavaDoc gọi các overload không nhận kích thước là *effectively unlimited*: chúng được thiết kế để cung cấp một lượng giá trị rất lớn cho đến khi pipeline dừng, chứ không có nghĩa chương trình được cấp bộ nhớ vô hạn hay phải tạo vô số đối tượng ngay khi gọi phương thức.

**Lưu ý:** Các số do `Random` tạo là *pseudorandom* (giả ngẫu nhiên). Java Stream không làm cho chúng trở thành số ngẫu nhiên mật mã. Hành vi xác suất, tái lập bằng seed và tính an toàn cho tác vụ bảo mật là những vấn đề riêng với kích thước luồng.

## 2. Các overload của Random: hữu hạn và không giới hạn sẵn

`java.util.Random` cung cấp các nhóm overload tương tự cho `ints`, `longs` và `doubles`:

| Phương thức mẫu | Số lượng phần tử | Khoảng giá trị |
|---|---|---|
| `random.ints()` | Không giới hạn sẵn | Toàn miền `int` |
| `random.ints(streamSize)` | Chính xác `streamSize` trước các phép loại bỏ | Toàn miền `int` |
| `random.ints(origin, bound)` | Không giới hạn sẵn | `origin <= x < bound` |
| `random.ints(streamSize, origin, bound)` | Chính xác `streamSize` trước các phép loại bỏ | `origin <= x < bound` |
| `random.longs(...)` | Cùng bốn dạng overload | Số `long` |
| `random.doubles(...)` | Cùng bốn dạng overload | Số `double` |

Với `doubles()` hay `doubles(streamSize)` không truyền khoảng, mỗi phần tử nằm trong `[0.0, 1.0)`. Với `ints()` và `longs()` không truyền khoảng, nguồn phát giá trị trên toàn miền của kiểu nguyên tương ứng.

Ví dụ:

~~~java
Random random = new Random();

IntStream anyIntegers = random.ints(8);
IntStream dice = random.ints(8, 1, 7);
LongStream ids = random.longs(8, 100L, 1000L);
DoubleStream fractions = random.doubles(8); // 0.0 <= x < 1.0
~~~

Các dòng trên là đoạn minh họa bên trong một phương thức, cần import `java.util.Random` và `java.util.stream.*`. Chúng mô tả **bốn stream tách biệt**. Stream chỉ nên được dùng cho một terminal operation; hãy tạo stream mới khi cần tính lại.

Không nhầm `random.ints(5)` với `random.ints(0, 5)`:

- `ints(5)` có **một tham số kích thước kiểu `long`**, tạo 5 số `int` trên toàn miền giá trị.
- `ints(0, 5)` có **hai tham số phạm vi kiểu `int`**, tạo luồng không giới hạn sẵn các số 0, 1, 2, 3 hoặc 4.
- `ints(5, 0, 5)` có **ba tham số**, tạo đúng 5 số trong `[0, 5)`.

Đây là lỗi rất dễ xảy ra vì `5` có thể được hiểu là số lượng hoặc một biên phạm vi tùy chữ ký phương thức.

## 3. Giới hạn kích thước ngay tại nguồn bằng streamSize

Muốn lấy đúng `n` lần sinh giá trị, cách ngắn gọn là dùng overload với `streamSize`:

~~~java
int[] fiveDice = new Random(42L)
        .ints(5, 1, 7)
        .toArray();
~~~

`fiveDice.length == 5`. Mọi phần tử thỏa `1 <= x && x < 7`. Tham số đầu tiên là **số phần tử**, hai tham số còn lại là **biên dưới bao gồm, biên trên loại trừ**.

Ví dụ về sự khác nhau giữa `streamSize` và khoảng:

~~~java
new Random().ints(5, 1, 7);    // Nguồn hữu hạn: 5 số trong [1,7)
new Random().ints(100, 1, 7);  // Nguồn hữu hạn: 100 số trong [1,7)
new Random().ints(5, 10);      // Nguồn không giới hạn sẵn: số trong [5,10)
~~~

Ba dòng khai báo trên chưa chạy terminal operation, vì vậy chúng không phải ví dụ in dữ liệu. Không nên tạo stream rồi vứt đi trong mã ứng dụng; ví dụ nhằm chỉ rõ ý nghĩa overload.

`streamSize` thuộc kiểu `long` và phải **không âm**. `streamSize = 0` tạo stream rỗng; giá trị âm làm ném `IllegalArgumentException`. Kích thước rất lớn tuy hợp lệ về mặt tham số có thể vẫn không khả thi nếu gọi `toArray()` hoặc gom tất cả phần tử vào bộ nhớ. Với xử lý tuần tự từng phần, `forEach` hoặc một phép gộp có thể tiêu thụ ít bộ nhớ hơn nhưng vẫn cần thời gian tương ứng số phần tử.

**Khi nào chọn overload hữu hạn?** Khi yêu cầu đã biết trước số mẫu, ví dụ tạo 500 giá trị làm fixture kiểm thử hoặc 20 giá trị cho báo cáo, cách này biểu đạt ý định rõ nhất.

## 4. Tạo luồng không giới hạn sẵn rồi dùng limit(n)

Phương thức `limit(long maxSize)` là một *intermediate operation* tạo pipeline có tối đa `maxSize` phần tử từ nguồn phía trước:

~~~java
int[] fiveDice = new Random(42L)
        .ints(1, 7)     // nguồn hiệu quả là vô hạn
        .limit(5)       // giới hạn tối đa 5 phần tử
        .toArray();     // kích hoạt sinh và thu thập
~~~

Với nguồn giả ngẫu nhiên luôn có đủ giá trị, `limit(5)` và không có phép loại bỏ sau đó sẽ tạo đúng 5 phần tử. Nhưng quy tắc tổng quát của `limit(n)` là **tối đa n**, không phải lúc nào cũng đúng n: nếu nguồn đã chỉ có 3 phần tử thì `limit(5)` vẫn chỉ thu được 3 phần tử.

Hai cách sau đều thể hiện ý định tạo 5 số thuộc `[1,7)`:

~~~java
new Random(42L).ints(5, 1, 7).toArray();        // Giới hạn ở nguồn
new Random(42L).ints(1, 7).limit(5).toArray();  // Giới hạn ở pipeline
~~~

Kết quả số cụ thể có thể khác theo thuật toán/kiểu bộ sinh và cách tiêu thụ nguồn, nhất là với parallel stream; với `java.util.Random` và cùng chuỗi gọi trên luồng tuần tự, seed cho phép tái lập chuỗi. **Chọn cách diễn đạt đúng quy tắc**, không chọn vì trông giống một dãy số cụ thể.

`limit(0)` trả stream rỗng; `limit(-1)` làm ném `IllegalArgumentException`. Nếu `n` do người dùng cung cấp, hãy kiểm tra `0 <= n <= maxAllowed` trước khi dựng pipeline, thay vì cho phép một yêu cầu khổng lồ chiếm CPU/bộ nhớ.

## 5. Ví dụ chạy độc lập Java 17+

Tạo tệp `RandomStreamSizeDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Random;

public class RandomStreamSizeDemo {
    public static void main(String[] args) {
        int[] five = new Random(42L).ints(5, 1, 7).toArray();
        System.out.println("five = " + Arrays.toString(five));
        System.out.println("five length = " + five.length);
        System.out.println("five bounds = "
                + Arrays.stream(five).allMatch(x -> x >= 1 && x < 7));

        int[] four = new Random(99L)
                .ints(0, 100)
                .limit(4)
                .toArray();
        System.out.println("four = " + Arrays.toString(four));
        System.out.println("four length = " + four.length);

        int[] tenEven = new Random(7L)
                .ints(0, 100)
                .filter(x -> x % 2 == 0)
                .limit(10)
                .toArray();
        System.out.println("tenEven length = " + tenEven.length);
        System.out.println("tenEven bounds = "
                + Arrays.stream(tenEven)
                        .allMatch(x -> x >= 0 && x < 100 && x % 2 == 0));

        int[] finiteFiltered = new Random(5L)
                .ints(6, 0, 10)
                .filter(x -> x >= 5)
                .toArray();
        System.out.println("finiteFiltered = "
                + Arrays.toString(finiteFiltered));
        System.out.println("finiteFiltered length = " + finiteFiltered.length);

        System.out.println("empty size = "
                + new Random(8L).ints(0, 10, 11).count());

        long[] longs = new Random(4L).longs(3, 10L, 20L).toArray();
        double[] doubles = new Random(4L)
                .doubles(3, 0.5, 1.5)
                .toArray();
        System.out.println("long bounds = "
                + Arrays.stream(longs).allMatch(x -> x >= 10L && x < 20L));
        System.out.println("double bounds = "
                + Arrays.stream(doubles).allMatch(x -> x >= 0.5 && x < 1.5));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RandomStreamSizeDemo.java
java RandomStreamSizeDemo
~~~

Một kết quả với `java.util.Random` theo thuật toán chuẩn:

~~~text
five = [3, 4, 1, 3, 1]
five length = 5
five bounds = true
four = [87, 58, 29, 11]
four length = 4
tenEven length = 10
tenEven bounds = true
finiteFiltered = [7, 6, 5]
finiteFiltered length = 3
empty size = 0
long bounds = true
double bounds = true
~~~

Ý nghĩa các phần:

1. `ints(5, 1, 7)` được cấp kích thước ở **nguồn**, nên thu được 5 số có mặt từ 1 đến 6. Giá trị xuất hiện lại, như số 3 và số 1, là hợp lệ: sinh ngẫu nhiên **không có nghĩa không trùng lặp**.
2. `ints(0, 100).limit(4)` dùng nguồn không giới hạn sẵn rồi lấy 4 phần tử.
3. `filter(even).limit(10)` tiếp tục sinh từ nguồn không giới hạn sẵn đến khi **nhận đủ 10 số chẵn** trong ví dụ này; số lần thử có thể lớn hơn 10.
4. `ints(6, 0, 10).filter(x >= 5)` bắt đầu từ **6 phần tử nguồn**, sau lọc chỉ còn 3 phần tử đối với seed đã chọn. Đặt kích thước ở nguồn không có nghĩa kết quả cuối sau `filter` vẫn phải chứa 6 phần tử.
5. `ints(0, 10, 11)` dùng `streamSize = 0`; terminal `count()` trả 0. Hai nguồn `longs`/`doubles` cũng hoạt động theo kích thước/phạm vi độc lập.

Ví dụ trên sử dụng seed chỉ để làm đầu ra dễ kiểm chứng. Không dùng seed cố định cho mục đích bảo mật hoặc trong sản phẩm khi yêu cầu dữ liệu khó đoán.

## 6. Phạm vi giá trị: origin bao gồm, bound loại trừ

Với overload có khoảng, quy tắc cơ bản là:

~~~text
origin <= value < bound
~~~

Ví dụ:

| Ý định | Lời gọi |
|---|---|
| Tung xúc xắc 20 lần, mỗi lần 1–6 | `random.ints(20, 1, 7)` |
| Lấy 10 số nguyên từ 0 đến 9 | `random.ints(10, 0, 10)` |
| Lấy 4 số nguyên từ -3 đến 3 | `random.ints(4, -3, 4)` |
| Lấy 5 số `long` trong [100, 200) | `random.longs(5, 100L, 200L)` |
| Lấy 6 số `double` trong [0.25, 0.75) | `random.doubles(6, 0.25, 0.75)` |

Truyền `origin >= bound` vào overload có khoảng gây `IllegalArgumentException`; việc đặt hai biên bằng nhau không tạo dòng toàn một số như nhiều người lầm tưởng. Đối với `double`, biên phải hữu hạn và khoảng hợp lệ; không dùng `Double.NaN` hoặc vô cực làm biên.

Cẩn thận khi muốn "bao gồm giá trị tối đa": với `int`, không cộng bừa `1` vào `Integer.MAX_VALUE`, vì tràn số sẽ làm hỏng khoảng. Tương tự, không dùng `(int)(Math.random() * range)` cho khoảng lớn nếu điều này gây lệch phân bố hoặc tràn số. Ưu tiên overload có `origin`/`bound` và kiểm tra rõ tình huống phải bao gồm biên cực đại.

Một khoảng có chỉ **một giá trị hợp lệ**, ví dụ `[5,6)`, sẽ cho toàn số 5. Đó là đúng hợp đồng, dù không tạo sự đa dạng. Muốn nhiều số khác nhau, cần khoảng đủ rộng và vẫn có thể xuất hiện trùng lặp.

## 7. Thứ tự filter và limit quyết định kích thước kết quả

`filter` loại các phần tử không đạt điều kiện; `limit` chặn số phần tử đi qua **đến vị trí đặt nó** trong pipeline. Vì thế hai chuỗi sau không tương đương:

~~~java
// A: lấy tối đa 10 phần tử nguồn, sau đó lọc chẵn
int[] a = new Random(7L)
        .ints(0, 100)
        .limit(10)
        .filter(x -> x % 2 == 0)
        .toArray();

// B: lọc chẵn trước, rồi lấy tối đa 10 số chẵn
int[] b = new Random(7L)
        .ints(0, 100)
        .filter(x -> x % 2 == 0)
        .limit(10)
        .toArray();
~~~

Các đoạn này cần `import java.util.Random;` và được đặt trong phương thức.

| Pipeline | Giới hạn đặt lên | Số phần tử đầu ra |
|---|---|---|
| `limit(10).filter(even)` | Tối đa 10 số nguồn | Có thể từ 0 đến 10 |
| `filter(even).limit(10)` | Tối đa 10 số **đã lọc** | 10 nếu nguồn cuối cùng cung cấp đủ số thỏa điều kiện và terminal hoàn tất |
| `ints(10, 0, 100).filter(even)` | Chính xác 10 số nguồn | Có thể từ 0 đến 10 |
| `ints(10, 0, 100)` | 10 số nguồn và không loại bỏ | Đúng 10 |

**Quy tắc ứng dụng:** nếu bài toán là **thử đúng 10 lần** rồi lấy những kết quả hợp lệ, đặt giới hạn nguồn trước `filter`. Nếu bài toán là **tìm tối đa 10 kết quả hợp lệ**, đặt `filter` trước `limit` và cân nhắc giới hạn số lần thử/tổng thời gian.

Với nguồn không giới hạn sẵn, `filter(...).limit(10)` có thể mất thời gian rất lâu hoặc không kết thúc nếu điều kiện không bao giờ đúng. Ví dụ `ints(1, 7).filter(x -> x == 7).limit(1)` sẽ không bao giờ tìm ra 7 vì nguồn chỉ sinh 1–6.

Để vừa giới hạn **số lần thử** vừa giới hạn **số kết quả hợp lệ**, dùng:

~~~java
int[] accepted = new Random()
        .ints(100, 0, 100)          // thử tối đa 100 mẫu
        .filter(x -> x > 95)        // chỉ giữ 96..99
        .limit(5)                   // tối đa 5 kết quả
        .toArray();
~~~

Kết quả có thể ít hơn 5 số nếu không đủ mẫu hợp lệ. Đây là cách xử lý có giới hạn chắc chắn về số mẫu được xét, thay vì chỉ dựa vào xác suất điều kiện cuối cùng xảy ra.

## 8. Stream là lazy: khi nào bộ sinh thực sự hoạt động?

Đoạn sau mới chỉ **mô tả pipeline**:

~~~java
Random random = new Random(42L);
IntStream stream = random.ints(1, 7).limit(3);
~~~

Nguồn phát số khi phần tử được yêu cầu trong terminal operation. Khi gọi:

~~~java
int[] values = stream.toArray();
~~~

pipeline mới cần tiêu thụ số từ nguồn.

Một điều dễ nhầm: `count()` không luôn buộc pipeline phải gọi bộ sinh từng lần. Một stream hữu hạn đã biết kích thước có thể cho phép thư viện tối ưu `count()` mà không cần tạo các phần tử. Vì vậy, **không dùng số lần chạy của `peek()` hoặc trạng thái bộ sinh sau `count()` để kiểm chứng việc nguồn đã phát bao nhiêu số**. Nếu cần kiểm tra giá trị thật, dùng `toArray()`, `forEach()` hoặc tính toán thực tế phụ thuộc giá trị.

Sau khi đã thực hiện terminal operation, stream đó **không thể tái sử dụng**:

~~~java
IntStream numbers = new Random().ints(5);
int[] first = numbers.toArray();

// numbers.sum(); // IllegalStateException: stream đã được dùng
~~~

Hãy tạo pipeline mới từ nguồn hoặc dùng supplier trả stream mới nếu cần chạy lại. Nếu cả hai pipeline dùng chung một đối tượng `Random`, trạng thái bộ sinh đã tiến lên khi được tiêu thụ; kết quả lần hai thường khác lần một.

## 9. Stream.generate và Math.random có thể dùng khi nào?

Ngoài `Random.ints(...)`, Java hỗ trợ:

~~~java
import java.util.stream.Stream;
import java.util.concurrent.ThreadLocalRandom;

int[] dice = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(1, 7))
        .limit(5)
        .mapToInt(Integer::intValue)
        .toArray();
~~~

`Stream.generate(Supplier<T>)` tạo một stream đối tượng **không giới hạn sẵn**; `limit(5)` biến phần cần thu thập thành hữu hạn. Với số primitive, `random.ints(5, 1, 7)` thường ngắn hơn, biểu đạt miền giá trị và tránh boxing/unboxing. `Stream.generate` có ích nếu phần tử phải là đối tượng phức tạp, ví dụ bộ dữ liệu giả lập gồm nhiều trường.

`Math.random()` trả một `double` từ 0 (bao gồm) đến 1 (loại trừ). Có thể viết `Stream.generate(Math::random).limit(5)` nhưng nó là `Stream<Double>` có boxing, và cách điều khiển seed không trực tiếp như tạo `new Random(seed)`. Không dùng `(int)(Math.random() * n)` một cách máy móc khi đã có API sinh số nguyên theo khoảng.

Từ Java 17, giao diện `java.util.random.RandomGenerator` chuẩn hóa API cho nhiều thuật toán bộ sinh. `java.util.Random` triển khai giao diện này. Khi cần lựa chọn thuật toán phù hợp hoặc loại bộ sinh đặc biệt để chạy song song, có thể thiết kế theo `RandomGenerator`; **bất kể bộ sinh nào, vẫn cần kiểm tra kích thước, khoảng và chất lượng ngẫu nhiên đúng mục đích**.

## 10. Seed và khả năng tái lập trong kiểm thử

Seed giúp kết quả giả ngẫu nhiên có thể được tạo lại khi giữ đúng thuật toán, cách gọi và thứ tự tiêu thụ. Ví dụ:

~~~java
int[] left = new Random(123L).ints(5, 0, 10).toArray();
int[] right = new Random(123L).ints(5, 0, 10).toArray();

System.out.println(Arrays.equals(left, right)); // true
~~~

Thêm `import java.util.Arrays;` bên cạnh `java.util.Random`.

Với `java.util.Random` cụ thể, thuật toán được Java xác định để bảo đảm tính lặp lại khi hai instance có seed giống nhau và cùng chuỗi thao tác. Tuy nhiên, không giả định mọi lớp triển khai `RandomGenerator` phải cho **cùng** dãy số với `Random`, hoặc cùng seed nhưng đổi thuật toán/parallelism sẽ cho cùng chuỗi.

Khi viết test, ưu tiên xác minh tính chất:

- **Kích thước:** đúng số phần tử cần tạo hoặc không vượt giới hạn áp đặt.
- **Biên:** mọi giá trị thuộc `[origin, bound)`.
- **Dữ liệu hợp lệ:** `filter`, `map` và các ràng buộc đều được đáp ứng.
- **Khả năng tái lập:** dùng seed và bộ sinh có xác định khi chính xác chuỗi là điều cần kiểm chứng.

Không dùng seed cố định để tạo token đăng nhập, mật khẩu tạm hoặc giá trị bảo mật. `Random` không được thiết kế để chống dự đoán; các trường hợp bảo mật cần API `SecureRandom` và thiết kế phù hợp.

## 11. Giới hạn kích thước và quản lý tài nguyên

**Không thu thập luồng không giới hạn sẵn nếu chưa chặn.** Ví dụ dưới đây nguy hiểm:

~~~java
// Không chạy:
new Random().ints().toArray();
~~~

Mảng cần được tạo có kích thước không có giới hạn khả thi và chương trình có thể hết bộ nhớ hoặc không thể hoàn tất. Một pipeline không giới hạn sẵn với phép toán terminal như `sum()` hoặc `forEach()` cũng có thể không kết thúc nếu không có điều kiện chặn.

Nếu chỉ cần một giá trị, dùng `random.nextInt(origin, bound)` của API phù hợp hoặc `random.ints(origin, bound).findAny()`, thay vì tạo tập lớn. Với một batch 50.000 phần tử mà chỉ cần thống kê, có thể xử lý trực tiếp:

~~~java
long numberOfEven = new Random()
        .ints(50_000, 0, 1_000)
        .filter(x -> x % 2 == 0)
        .count();
~~~

Do `filter` loại phần tử tùy giá trị, ở đây terminal phải xác định số phần tử đạt điều kiện; tổng số đầu vào hữu hạn rõ ràng. Không dùng `count()` của pipeline đơn thuần để kết luận tất cả phần tử đã được hiện thực hóa.

**Giới hạn do người dùng nhập:** kiểm tra giới hạn kích thước theo tài nguyên trước khi gọi nguồn. Một số `streamSize` hợp lệ kiểu `long` có thể vượt khả năng tạo mảng Java; `limit` không đồng nghĩa miễn phí về bộ nhớ nếu tiếp theo gọi `toArray()`.

**Không sắp xếp toàn bộ nguồn vô hạn:** `random.ints().sorted().limit(10)` cần biết thứ tự toàn bộ đầu vào trước khi chọn phần tử theo thứ tự nên không hoàn tất hữu ích. Ngược lại:

~~~java
int[] orderedSample = new Random()
        .ints(0, 100)
        .limit(10)
        .sorted()
        .toArray();
~~~

Cách này lấy mẫu hữu hạn **trước**, rồi sắp xếp chính các mẫu đã lấy. Nó không tìm ra "10 số nhỏ nhất trong vô hạn số" và cũng không bảo đảm không trùng lặp.

**`distinct()` và miền hữu hạn:** nguồn `ints(1, 7)` chỉ có 6 giá trị phân biệt. `distinct().limit(7)` trên nguồn này sẽ không bao giờ thu đủ 7 giá trị. Nếu muốn chọn 6 số duy nhất từ 1–6, hãy lấy một tập hữu hạn rồi xáo trộn bằng phương pháp phù hợp, hoặc dùng cách chọn không hoàn lại; sinh từng số ngẫu nhiên không tự bảo đảm tính duy nhất.

## 12. Xử lý parallel stream thận trọng

Có thể gọi `parallel()` trên stream, nhưng **không phải cứ bật parallel là nhanh hơn hoặc dễ tái lập hơn**:

~~~java
long count = new Random()
        .ints(100_000, 0, 1_000)
        .parallel()
        .filter(x -> x % 2 == 0)
        .count();
~~~

`Random` là thread-safe, nhưng nhiều luồng dùng chung bộ sinh có thể tranh chấp trạng thái và làm giảm hiệu năng. Thứ tự lấy số trong parallel stream có thể thay đổi theo lịch thực thi, nên **seed giống nhau không đủ để đảm bảo dãy phần tử/đầu ra giống hệt nhau khi xử lý song song**. Tránh test dựa trên đúng dãy số sau `parallel()` trừ khi bạn đã cố định, kiểm chứng và chấp nhận đầy đủ hợp đồng thứ tự của thuật toán/bộ sinh được chọn.

Trong bài toán hiệu năng cao trên nhiều luồng, xem xét `ThreadLocalRandom` hoặc bộ sinh thuộc nhóm `RandomGenerator.SplittableGenerator` như `SplittableRandom` với cách tách trạng thái phù hợp. Không dùng một `SplittableRandom` đơn lẻ đồng thời trên nhiều thread nếu không có thiết kế quản lý thread rõ ràng.

`limit()` với một stream có thứ tự gặp (*encounter order*) có thể tốn chi phí phối hợp lớn hơn ở parallel mode vì phải giữ đúng phần tử đầu tiên; với một nguồn không có thứ tự gặp, các bảo đảm và lựa chọn phần tử có thể khác. Do đó:
- Xác định xem kết quả cần thứ tự hay chỉ cần đặc tính tổng hợp.
- Benchmark trên dữ liệu thực tế trước khi chọn parallel.
- Giữ dữ liệu thao tác trong các lambda không can thiệp trạng thái nguồn và tránh side effect dùng chung.

Với các bài học hoặc batch số lượng vừa phải, stream **tuần tự** thường dễ giải thích và kiểm chứng nhất.

## 13. Lỗi tham số và tình huống biên

| Trường hợp | Kết quả / xử lý |
|---|---|
| `new Random().ints(0, 1, 7)` | Stream rỗng, không có mẫu |
| `new Random().ints(-1, 1, 7)` | `IllegalArgumentException`: kích thước âm |
| `new Random().ints(5, 7, 7)` | `IllegalArgumentException`: biên dưới không nhỏ hơn biên trên |
| `new Random().ints(1, 7).limit(-1)` | `IllegalArgumentException`: limit âm |
| `new Random().doubles(5, Double.NaN, 1.0)` | `IllegalArgumentException`: biên không hợp lệ |
| `new Random().ints(1, 7).limit(0)` | Stream rỗng |
| `new Random().ints(3, 1, 7).limit(5)` | Nhiều nhất 3 phần tử, không tự sinh thêm thành 5 |
| `new Random().ints(3, 1, 7).filter(x -> false)` | Không phần tử nào đi qua filter |

Đặc biệt với `int` và `long`, phép trừ `bound - origin` có thể bị tràn trong mã tự tính khoảng. Các overload `Random.ints(origin, bound)` và `longs(origin, bound)` được viết để xử lý trường hợp miền hợp lệ khó biểu diễn bằng phép trừ đơn giản. Hãy kiểm tra `origin < bound` và ưu tiên API thay vì xây công thức tự nhân chia bằng kiểu số nguyên có thể tràn.

Khi giới hạn số phần tử đầu ra cần **chính xác**, ghi rõ có phép `filter` hay `distinct` sau khi giới hạn. Nhiều phép biến đổi chỉ thay giá trị (ví dụ `map`) giữ số lượng; một số phép khác như `filter`/`distinct` có thể làm giảm số lượng.

## 14. Hai tình huống áp dụng hoàn chỉnh

### A. Sinh 12 lượt xúc xắc để tính tổng

~~~java
Random rng = new Random(2026L);
int total = rng.ints(12, 1, 7).sum();
System.out.println(total);
~~~

Đoạn đặt trong phương thức với `import java.util.Random;`. `sum()` tiêu thụ stream hữu hạn gồm 12 mặt xúc xắc (có thể trùng). Không phải lấy 12 mặt duy nhất. Với mẫu lớn hoặc giá trị có độ lớn lớn, cần cân nhắc tràn `int` khi dùng `sum()`; có thể chuyển sang `mapToLong` hoặc phép cộng kiểm tra tràn theo yêu cầu.

### B. Tạo tối đa 20 giá trị hợp lệ từ tối đa 1.000 lần thử

~~~java
Random rng = new Random();
int[] accepted = rng.ints(1_000, 0, 10_000)
        .filter(x -> x % 10 == 0)
        .limit(20)
        .toArray();
System.out.println("accepted = " + accepted.length);
~~~

Ví dụ này có hai giới hạn độc lập: không lấy quá 1.000 mẫu nguồn và không giữ quá 20 kết quả sau lọc. Nếu yêu cầu hệ thống là **bắt buộc có đủ 20 kết quả**, hãy xử lý trường hợp `accepted.length < 20` bằng chiến lược ứng dụng rõ ràng (ví dụ báo thiếu mẫu, tăng số lần thử có giới hạn, hoặc chuyển sang thuật toán khác). Không giả định xác suất sẽ luôn cung cấp đủ giá trị.

## 15. Tự kiểm tra

**Câu 1:** `new Random().ints(5, 10)` có bao nhiêu phần tử trước khi giới hạn?

**Đáp án:** Không có giới hạn kích thước truyền vào; đây là overload nhận `origin = 5`, `bound = 10`. Nguồn phát các số 5–9 và được xem là không giới hạn sẵn. Muốn tạo 5 số trong khoảng này, viết `ints(5, 5, 10)` hoặc `ints(5, 10).limit(5)`.

**Câu 2:** `random.ints(10, 1, 7).filter(x -> x == 6).count()` luôn trả 10?

**Đáp án:** Không. 10 là số lần lấy mẫu ban đầu; sau lọc chỉ những lần xuất hiện số 6 được đếm. Kết quả nằm trong `[0,10]`.

**Câu 3:** `random.ints(1, 7).filter(x -> x == 7).limit(1).findFirst()` có đảm bảo kết thúc?

**Đáp án:** Không. Khoảng `[1,7)` không chứa 7; bộ lọc không bao giờ chấp nhận một giá trị nào. Cần kiểm soát phạm vi và tối đa số lần thử.

**Câu 4:** Có nên dùng `random.ints().sorted().limit(10).toArray()` để lấy 10 số nhỏ nhất?

**Đáp án:** Không. `sorted()` cần tiêu thụ toàn bộ đầu vào để sắp xếp nên một nguồn không giới hạn sẵn không thể xử lý theo cách đó. Nếu muốn sắp 10 mẫu, dùng `ints().limit(10).sorted().toArray()`.

**Câu 5:** Hai đối tượng `new Random(42)` và `new Random(42)` chạy tuần tự, cùng pipeline `ints(5,1,7).toArray()` có thể tạo cùng kết quả không?

**Đáp án:** Có, với `java.util.Random` cùng seed và chuỗi lời gọi theo hợp đồng. Không mở rộng kết luận thành "mọi thuật toán bộ sinh và mọi parallel stream đều tạo cùng kết quả chỉ vì seed giống nhau".

**Câu 6:** Nếu yêu cầu "không có hơn 100 lượt thử nhưng cần tối đa 5 số chẵn", nên đặt `limit` ở đâu?

**Đáp án:** Dùng nguồn hữu hạn `ints(100, origin, bound)`, tiếp theo `filter(even).limit(5)`. Kết quả có thể ít hơn 5 nếu 100 lượt thử chưa tạo đủ số chẵn; giới hạn số lần thử vẫn được giữ.

## 16. Ghi nhớ và tài liệu chính thức

- `ints(streamSize, origin, bound)` là lựa chọn trực tiếp cho **kích thước và miền giá trị đều biết trước**.
- `ints(origin, bound).limit(n)` hợp lý khi nguồn không giới hạn sẵn cần chặn lại ở pipeline; luôn có terminal operation khi thực sự muốn xử lý.
- `origin` được **bao gồm**, `bound` bị **loại trừ**; `streamSize` và `limit` không âm. `limit(n)` đặt **trần n phần tử ở đúng vị trí** của nó, chứ không bảo đảm đủ n phần tử sau các bước lọc.
- Luồng xử lý lazy; `count()` có thể được tối ưu khi nguồn đã có kích thước biết trước. Đừng dựa vào side effect trong pipeline để suy ra chắc chắn mọi giá trị đã được sinh.
- Giới hạn cả số lần thử, số kết quả và tài nguyên; dùng bộ sinh thích hợp với mục đích, đặc biệt nếu có xử lý song song hoặc yêu cầu mật mã.

Tài liệu tham khảo:
- [Random — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): overload `ints`, `longs`, `doubles`, validation và khả năng tái lập bằng seed.
- [IntStream — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): terminal và intermediate operation trên số `int`.
- [Stream — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): lazy evaluation, `filter`, `limit`, `sorted`, `count` và xử lý song song.
- [RandomGenerator — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): giao diện bộ sinh có dòng giá trị ngẫu nhiên kể từ Java 17.
